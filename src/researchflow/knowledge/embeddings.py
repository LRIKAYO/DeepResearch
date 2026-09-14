import math
import os
from typing import Any

from langchain_openai import OpenAIEmbeddings


EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 1024


def build_embeddings() -> OpenAIEmbeddings:
    model = _require_env("SILICONFLOW_EMBEDDING_MODEL")
    if model != EMBEDDING_MODEL:
        raise ValueError(f"SILICONFLOW_EMBEDDING_MODEL must be {EMBEDDING_MODEL}")
    return OpenAIEmbeddings(
        api_key=_require_env("SILICONFLOW_API_KEY"),
        base_url=_require_env("SILICONFLOW_BASE_URL"),
        model=model,
        check_embedding_ctx_length=False,
    )


def embed_documents(client: Any, texts: list[str]) -> list[list[float]]:
    return _validate_vectors(client.embed_documents(texts), expected_count=len(texts))


def embed_query(client: Any, text: str) -> list[float]:
    return _validate_vectors([client.embed_query(text)], expected_count=1)[0]


def _validate_vectors(raw_vectors: Any, *, expected_count: int) -> list[list[float]]:
    if not isinstance(raw_vectors, list) or len(raw_vectors) != expected_count:
        raise ValueError("Invalid embedding result count")

    vectors: list[list[float]] = []
    for raw_vector in raw_vectors:
        if not isinstance(raw_vector, list) or len(raw_vector) != EMBEDDING_DIMENSION:
            raise ValueError("Invalid embedding dimension")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in raw_vector
        ):
            raise ValueError("Embedding contains a non-finite numeric value")
        vector = [float(value) for value in raw_vector]
        if math.hypot(*vector) == 0:
            raise ValueError("Embedding vector must be non-zero")
        vectors.append(vector)
    return vectors


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value
