from collections.abc import Callable
from typing import Any

from fastapi import Depends
from typing_extensions import Annotated

from researchflow.knowledge.embeddings import build_embeddings


EmbeddingFactory = Callable[[], Any]


def get_embedding_factory() -> EmbeddingFactory:
    return build_embeddings


EmbeddingFactoryDependency = Annotated[
    EmbeddingFactory,
    Depends(get_embedding_factory),
]
