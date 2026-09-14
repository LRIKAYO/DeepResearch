from researchflow.backend.models import Base, Document, DocumentChunk
from researchflow.backend.projects import Project


def test_knowledge_models_keep_scope_on_project_and_use_fixed_vectors():
    assert Project.__table__.c.owner_user_id.nullable is False
    assert "owner_user_id" not in Document.__table__.c
    assert "project_id" not in DocumentChunk.__table__.c
    assert DocumentChunk.__table__.c.embedding.type.dim == 1024

    knowledge_indexes = {
        index.name
        for table_name in ("documents", "document_chunks")
        for index in Base.metadata.tables[table_name].indexes
    }
    assert knowledge_indexes == {
        "ix_documents_project_id",
        "ix_document_chunks_document_id",
    }
