import math

import pytest

from researchflow.knowledge.embeddings import (
    EMBEDDING_DIMENSION,
    embed_documents,
    embed_query,
)


class FakeEmbeddings:
    def __init__(self, document_vectors=None, query_vector=None):
        self.document_vectors = document_vectors
        self.query_vector = query_vector

    def embed_documents(self, texts):
        return self.document_vectors

    def embed_query(self, text):
        return self.query_vector


def vector(first=1.0):
    return [first, *([0.0] * (EMBEDDING_DIMENSION - 1))]


def test_accepts_valid_document_and_query_vectors():
    client = FakeEmbeddings([vector(), vector(2.0)], vector(3.0))

    assert embed_documents(client, ["one", "two"]) == [vector(), vector(2.0)]
    assert embed_query(client, "query") == vector(3.0)


@pytest.mark.parametrize(
    "bad_vectors",
    [
        None,
        [],
        [vector(), vector()],
        [[1.0]],
        [[0.0] * EMBEDDING_DIMENSION],
        [[math.nan, *([0.0] * (EMBEDDING_DIMENSION - 1))]],
        [[math.inf, *([0.0] * (EMBEDDING_DIMENSION - 1))]],
        [[True, *([0.0] * (EMBEDDING_DIMENSION - 1))]],
    ],
)
def test_rejects_invalid_document_vectors(bad_vectors):
    with pytest.raises(ValueError):
        embed_documents(FakeEmbeddings(document_vectors=bad_vectors), ["one"])


def test_rejects_invalid_query_vector():
    with pytest.raises(ValueError):
        embed_query(FakeEmbeddings(query_vector=[1.0]), "query")
