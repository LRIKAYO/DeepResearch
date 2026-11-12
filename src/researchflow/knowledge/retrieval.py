"""Project-scoped knowledge retrieval with cosine + BM25 fusion.

Retrieval considers exactly the chunks of one Project owned by one user. Two
independent rankings are produced over that same candidate set:

* exact cosine similarity between the query embedding and each chunk embedding
  (the ranking the Product Backend had before hybrid search existed), and
* BM25 over the chunk text, computed in-process with no extra dependency.

Cosine similarities and BM25 scores are not comparable magnitudes, so they are
fused with Reciprocal Rank Fusion (RRF): each candidate contributes
``1 / (RRF_K + rank)`` once per ranking it appears in. RRF needs only the order,
so neither score needs normalisation.

The ``KnowledgeHit.score`` field deliberately stays the *cosine similarity* of
the returned chunk, not its RRF score. The abstain policy compares the top
returned ``score`` against a cosine threshold (0.60 by default); returning an
RRF value there would silently redefine that threshold. One consequence is that
returned scores need not be non-increasing in rank order: lexical evidence can
promote a chunk whose cosine similarity is lower than the chunk after it.
"""

from __future__ import annotations

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


RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75

# A word token is a run of ASCII letters, digits and underscores. Identifiers in
# technical documentation are the discriminative signal ("baseNameMatch"), so a
# token is indexed both whole and split into its constituent words. The split
# keeps camelCase and snake_case searchable without a stemming dependency.
_TOKEN = re.compile(r"[A-Za-z0-9_]+")
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
    """Lowercase word tokens, plus the camelCase/snake_case parts of each one."""

    tokens: list[str] = []
    for match in _TOKEN.finditer(text):
        raw = match.group(0)
        whole = raw.lower()
        tokens.append(whole)
        for piece in raw.split("_"):
            if not piece:
                continue
            for part in _CAMEL_BOUNDARY.split(piece):
                part = part.lower()
                if part and part != whole:
                    tokens.append(part)
    return tokens


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
    counts = [Counter(tokens) for tokens in tokenized]
    lengths = [len(tokens) for tokens in tokenized]
    total_length = sum(lengths)
    average_length = total_length / len(documents) if total_length else 1.0
    document_frequency: Counter[str] = Counter()
    for token_counts in counts:
        document_frequency.update(token_counts.keys())

    scores = [0.0] * len(documents)
    for term in query_terms:
        frequency = document_frequency.get(term, 0)
        if frequency == 0:
            continue
        # The +1 keeps the IDF positive even for a term found in every chunk.
        inverse_document_frequency = math.log(
            1.0 + (len(documents) - frequency + 0.5) / (frequency + 0.5)
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


def search_knowledge(
    session: Session,
    *,
    owner_user_id: UUID,
    project_id: UUID,
    query_text: str,
    query_vector: list[float],
    limit: int,
    use_lexical: bool = True,
) -> list[KnowledgeHit]:
    """Search one owner-scoped Project and return the fused top ``limit`` hits.

    The SQL statement filters by Project *and* owner before any row leaves the
    database, and it deliberately has no ``LIMIT``: BM25 must see every chunk of
    this one Project to rank it fairly, and the lexical candidate set is still
    exactly the rows a cosine-only search would have been allowed to examine.
    A Project holds hundreds, not millions, of chunks, so scoring in memory per
    request is acceptable and keeps the implementation dependency-free.

    ``use_lexical=False`` keeps the exact-cosine behaviour, which the evaluation
    uses to measure what the lexical signal actually contributes.

    Query-language fallback: this corpus is English but the embedding model is
    multilingual. BM25 tokenises only Latin word tokens, so for a CJK query its
    ranking would be built from a handful of incidental Latin identifiers, not
    from the query as written. Fusing that partial signal measurably hurt
    cross-lingual recall, so a query containing CJK characters keeps the pure
    cosine ranking; bge-m3 is the component that actually handles that language
    pair, and BM25 has nothing to contribute to English chunks.
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

    # Rows are already in cosine order, so the row index *is* the cosine rank.
    cosine_ranking = list(range(len(rows)))
    lexical_ranking: list[int] = []
    if use_lexical and not _CJK.search(query_text):
        lexical_scores = bm25_scores(query_text, contents)
        lexical_ranking = sorted(
            (index for index, score in enumerate(lexical_scores) if score > 0.0),
            key=lambda index: (-lexical_scores[index], index),
        )
    fused = reciprocal_rank_fusion(cosine_ranking, lexical_ranking)

    return [
        KnowledgeHit(
            document_id=rows[index].document_id,
            chunk_id=rows[index].chunk_id,
            filename=rows[index].filename,
            content=rows[index].content,
            score=cosine_similarities[index],
        )
        for index in fused[:limit]
    ]
