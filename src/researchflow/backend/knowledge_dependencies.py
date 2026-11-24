from collections.abc import Callable
from typing import Any

from fastapi import Depends
from typing_extensions import Annotated

from researchflow.knowledge.embeddings import build_embeddings
from researchflow.knowledge.rerank import Reranker, build_reranker


EmbeddingFactory = Callable[[], Any]
RerankerFactory = Callable[[], Reranker | None]


def get_embedding_factory() -> EmbeddingFactory:
    return build_embeddings


def get_reranker_factory() -> RerankerFactory:
    return build_reranker


EmbeddingFactoryDependency = Annotated[
    EmbeddingFactory,
    Depends(get_embedding_factory),
]

RerankerFactoryDependency = Annotated[
    RerankerFactory,
    Depends(get_reranker_factory),
]
