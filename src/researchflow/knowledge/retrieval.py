"""Project-scoped knowledge retrieval with cosine + BM25 fusion and optional reranking.

Retrieval considers exactly the chunks of one Project owned by one user. Two
independent rankings are produced over that same candidate set:

* exact cosine similarity between the query embedding and each chunk embedding
  (the ranking the Product Backend had before hybrid search existed), and
* Okapi BM25 over the chunk text (Latin identifier splitting plus CJK character
  bigrams), computed in-process with no extra dependency.

Cosine similarities and BM25 scores are not comparable magnitudes, so they are
fused with Reciprocal Rank Fusion (RRF): each candidate contributes
``1 / (RRF_K + rank)`` once per ranking it appears in. RRF needs only the order,
so neither score needs normalisation. When a ``Reranker`` is configured, the top
RRF candidate pool (20 by default) is reordered by the cross-encoder before
slicing to ``limit``; any reranker error falls back cleanly to RRF order.

The ``KnowledgeHit.score`` field deliberately stays the *cosine similarity* of
the returned chunk, never its RRF score or cross-encoder relevance logit. The
abstain policy compares the best returned ``score`` against a cosine threshold
(0.60 by default); returning another scale there would silently break that
calibration. One consequence is that returned scores need not be non-increasing
in rank order: lexical evidence or cross-encoder reranking can promote a chunk
whose cosine similarity is lower than the chunk after it.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchflow.backend.models import Document, DocumentChunk
from researchflow.backend.projects import Project
from researchflow.knowledge.rerank import (
    MAX_RERANK_CANDIDATES,
    Reranker,
    rerank_candidate_count,
)


logger = logging.getLogger(__name__)

RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75

# ASCII identifiers in technical documentation are discriminative signals
# ("baseNameMatch"), so each ASCII run is indexed both whole and split on
# snake_case / camelCase boundaries. Contiguous CJK Unified Ideograph runs are
# indexed as overlapping character bigrams (or a unigram for a single-character
# run), giving dictionary-free Chinese & mixed-language lexical matching while
# stopping cleanly at CJK punctuation boundaries.
_TOKEN_OR_CJK = re.compile(r"([A-Za-z0-9_]+)|([\u3400-\u4dbf\u4e00-\u9fff]+)")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True)
class KnowledgeHit:
    document_id: UUID
    chunk_id: UUID
    filename: str
    content: str
    score: float


def tokenize(text: str) -> list[str]:
    """Emit lowercase ASCII identifier tokens (whole + camel/snake parts) and CJK bigrams."""

    tokens: list[str] = []
    for match in _TOKEN_OR_CJK.finditer(text):
        latin_raw, cjk_run = match.groups()
        if latin_raw is not None:
            whole = latin_raw.lower()
            tokens.append(whole)
            for piece in latin_raw.split("_"):
                if not piece:
                    continue
                for part in _CAMEL_BOUNDARY.split(piece):
                    part = part.lower()
                    if part and part != whole:
                        tokens.append(part)
        elif cjk_run is not None:
            if len(cjk_run) == 1:
                tokens.append(cjk_run)
            else:
                tokens.extend(
                    cjk_run[index : index + 2] for index in range(len(cjk_run) - 1)
                )
    return tokens


def _bm25_from_tokenized(
    query_terms: Sequence[str],
    tokenized_documents: Sequence[Sequence[str]],
    *,
    k1: float = BM25_K1,
    b: float = BM25_B,
    document_frequency: Counter[str] | None = None,
) -> list[float]:
    counts = [Counter(tokens) for tokens in tokenized_documents]
    lengths = [len(tokens) for tokens in tokenized_documents]
    total_length = sum(lengths)
    average_length = total_length / len(tokenized_documents) if total_length else 1.0
    if document_frequency is None:
        document_frequency = Counter()
        for token_counts in counts:
            document_frequency.update(token_counts.keys())

    scores = [0.0] * len(tokenized_documents)
    for term in query_terms:
        frequency = document_frequency.get(term, 0)
        if frequency == 0:
            continue
        # The +1 keeps the IDF positive even for a term found in every chunk.
        inverse_document_frequency = math.log(
            1.0 + (len(tokenized_documents) - frequency + 0.5) / (frequency + 0.5)
        )
        for index, token_counts in enumerate(counts):
            term_frequency = token_counts.get(term, 0)
            if term_frequency == 0:
                continue
            length_normalisation = 1.0 - b + b * (lengths[index] / average_length)
            denominator = term_frequency + k1 * length_normalisation
            scores[index] += (
                inverse_document_frequency
                * (term_frequency * (k1 + 1.0))
                / denominator
            )
    return scores


def bm25_scores(
    query: str,
    documents: Sequence[str],
    *,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> list[float]:
    """Score every document against the query with Okapi BM25.

    Repeated query terms are counted once; BM25's saturation term already
    captures term frequency on the document side. Documents whose text shares no
    token with the query score exactly ``0.0``, which the caller uses to tell
    "the lexical signal found nothing" apart from "the lexical signal found
    candidates".
    """

    if not documents:
        return []
    query_terms = tuple(dict.fromkeys(tokenize(query)))
    if not query_terms:
        return [0.0] * len(documents)

    tokenized = [tokenize(document) for document in documents]
    return _bm25_from_tokenized(query_terms, tokenized, k1=k1, b=b)


def _lexical_ranking(query_text: str, contents: Sequence[str]) -> list[int]:
    """Build the BM25 ranking while protecting CJK->English cross-lingual queries.

    When a query contains CJK characters:
    * Against a Chinese or bilingual corpus where CJK query terms actually match
      document text, full CJK-bigram + Latin-identifier BM25 runs so Chinese
      hybrid search works genuinely.
    * Against an English corpus (0 CJK characters, or only stray CJK badges like
      ``[简体中文]`` that share no CJK token with the query), BM25 would rank
      solely on incidental Latin identifiers embedded in the Chinese question,
      which measurably hurts cross-lingual recall on ``retrieval_v4``. Skipping
      BM25 there lets multilingual ``bge-m3`` handle the cross-lingual alignment.
    """

    query_has_cjk = bool(_CJK.search(query_text))
    if query_has_cjk and not any(_CJK.search(content) for content in contents):
        return []

    query_terms = tuple(dict.fromkeys(tokenize(query_text)))
    if not query_terms:
        return []

    tokenized = [tokenize(content) for content in contents]
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    if query_has_cjk:
        has_cjk_overlap = any(
            term in document_frequency for term in query_terms if _CJK.search(term)
        )
        if not has_cjk_overlap:
            return []

    lexical_scores = _bm25_from_tokenized(
        query_terms,
        tokenized,
        document_frequency=document_frequency,
    )
    return sorted(
        (index for index, score in enumerate(lexical_scores) if score > 0.0),
        key=lambda index: (-lexical_scores[index], index),
    )


def reciprocal_rank_fusion(
    cosine_ranking: Sequence[int],
    lexical_ranking: Sequence[int],
    *,
    k: int = RRF_K,
) -> list[int]:
    """Fuse two rankings of the same candidate indices.

    Both rankings are expected to hold candidate indices in descending
    relevance order (1-based ranks inside). Ties are broken by candidate index,
    which the caller assigns in cosine order, so an exact tie falls back to the
    pre-hybrid ordering instead of becoming non-deterministic.
    """

    fused: dict[int, float] = {}
    for ranking in (cosine_ranking, lexical_ranking):
        for rank, index in enumerate(ranking, start=1):
            fused[index] = fused.get(index, 0.0) + 1.0 / (k + rank)
    return sorted(fused, key=lambda index: (-fused[index], index))


def rank_candidates(
    query_text: str,
    contents: Sequence[str],
    *,
    limit: int,
    use_lexical: bool = True,
    reranker: Reranker | None = None,
    rerank_candidates: int | None = None,
) -> list[int]:
    """Return top ``limit`` indices into ``contents`` (assumed pre-sorted by cosine)."""

    if not contents or limit < 1:
        return []

    cosine_ranking = list(range(len(contents)))
    lexical_ranking = _lexical_ranking(query_text, contents) if use_lexical else []
    fused = reciprocal_rank_fusion(cosine_ranking, lexical_ranking)

    if reranker is None:
        return fused[:limit]

    try:
        if rerank_candidates is None:
            pool_size = rerank_candidate_count(limit)
        else:
            pool_size = min(MAX_RERANK_CANDIDATES, max(limit, rerank_candidates))

        candidate_indices = fused[:pool_size]
        if len(candidate_indices) <= 1:
            return candidate_indices[:limit]

        top_n = min(limit, len(candidate_indices))
        candidate_texts = [contents[index] for index in candidate_indices]
        order = reranker.rerank(query_text, candidate_texts, top_n=top_n)
        if isinstance(order, (str, bytes)) or not isinstance(order, Sequence) or not order:
            raise ValueError("Reranker must return a non-empty sequence of indices")

        seen_positions: set[int] = set()
        reranked: list[int] = []
        for position in order:
            if (
                isinstance(position, bool)
                or not isinstance(position, int)
                or not 0 <= position < len(candidate_indices)
                or position in seen_positions
            ):
                raise ValueError(f"Invalid reranker candidate position: {position!r}")
            seen_positions.add(position)
            reranked.append(candidate_indices[position])

        if len(reranked) < top_n:
            seen_rows = set(reranked)
            reranked.extend(
                row_idx for row_idx in candidate_indices if row_idx not in seen_rows
            )
        return reranked[:limit]
    except Exception:
        logger.warning(
            "Reranker failed; falling back to RRF ranking",
            exc_info=True,
        )
        return fused[:limit]


def search_knowledge(
    session: Session,
    *,
    owner_user_id: UUID,
    project_id: UUID,
    query_text: str,
    query_vector: list[float],
    limit: int,
    use_lexical: bool = True,
    reranker: Reranker | None = None,
    rerank_candidates: int | None = None,
) -> list[KnowledgeHit]:
    """Search one owner-scoped Project and return the top ``limit`` hits.

    The SQL statement filters by Project *and* owner before any row leaves the
    database, and it deliberately has no ``LIMIT``: BM25 must see every chunk of
    this one Project to rank it fairly, and the lexical candidate set is still
    exactly the rows a cosine-only search would have been allowed to examine.
    A Project holds hundreds, not millions, of chunks, so scoring in memory per
    request is acceptable and keeps the implementation dependency-free.

    ``use_lexical=False`` keeps the exact-cosine behaviour, which the evaluation
    uses to measure what the lexical signal actually contributes.

    Cross-lingual safeguard: when a query contains CJK characters, BM25 is
    included in RRF whenever CJK query tokens actually appear in the Project's
    chunks (Chinese or bilingual corpora), and skipped when the Project contains
    no matching CJK tokens (pure-English corpora, or English READMEs with only a
    stray ``[简体中文]`` badge), preventing incidental Latin identifiers in a
    Chinese question from distorting ``bge-m3`` cross-lingual alignment.

    Optional reranking: when ``reranker`` is provided, the top RRF candidate
    pool (``RESEARCHFLOW_RERANK_CANDIDATES``, default 20) is reordered by the
    cross-encoder before taking ``limit`` hits. Any reranker failure logs a
    warning and falls back to RRF order, and ``KnowledgeHit.score`` always stays
    the chunk's exact cosine similarity.
    """

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(
            Document.document_id,
            DocumentChunk.chunk_id,
            Document.filename,
            DocumentChunk.content,
            distance.label("distance"),
        )
        .join(Document, Document.document_id == DocumentChunk.document_id)
        .join(Project, Project.project_id == Document.project_id)
        .where(
            Document.project_id == project_id,
            Project.owner_user_id == owner_user_id,
        )
        .order_by(distance.asc(), DocumentChunk.chunk_id.asc())
    )
    rows = session.execute(statement).all()
    if not rows:
        return []

    contents = [row.content for row in rows]
    cosine_similarities = [1.0 - float(row.distance) for row in rows]

    selected = rank_candidates(
        query_text,
        contents,
        limit=limit,
        use_lexical=use_lexical,
        reranker=reranker,
        rerank_candidates=rerank_candidates,
    )

    return [
        KnowledgeHit(
            document_id=rows[index].document_id,
            chunk_id=rows[index].chunk_id,
            filename=rows[index].filename,
            content=rows[index].content,
            score=cosine_similarities[index],
        )
        for index in selected
    ]
