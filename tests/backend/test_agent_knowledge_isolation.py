from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from researchflow.agent.graph import build_graph
from researchflow.agent.knowledge_search import (
    KNOWLEDGE_TIMEOUT_SECONDS,
    KnowledgeClient,
    KnowledgeScope,
)
from researchflow.agent.state import AgentContext
from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.knowledge_dependencies import get_embedding_factory
from researchflow.backend.models import Document, DocumentChunk
from researchflow.backend.projects import Project


QUERY_VECTOR = [1.0, *([0.0] * 1023)]


class FakeEmbeddings:
    def embed_query(self, query: str) -> list[float]:
        return QUERY_VECTOR


class FakeResearcherModel:
    def bind_tools(self, tools, **kwargs):
        assert [tool.name for tool in tools] == ["web_search", "knowledge_search"]
        assert kwargs == {"parallel_tool_calls": True}
        return self

    def invoke(self, messages):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "knowledge_search",
                    "args": {"query": "project evidence", "limit": 5},
                    "id": "knowledge-call",
                    "type": "tool_call",
                }
            ],
        )


class UnusedWebTool:
    name = "web_search"

    def invoke(self, args):
        raise AssertionError("web_search must not run in this smoke")


class RecordingWriter:
    def __init__(self):
        self.payloads = []

    def invoke(self, payload):
        self.payloads.append(payload)
        return "report"


def add_project_chunk(owner_user_id, label):
    project_id = uuid4()
    document_id = uuid4()
    with SessionLocal.begin() as session:
        session.add(
            Project(
                project_id=project_id,
                owner_user_id=owner_user_id,
                name=label,
            )
        )
        session.flush()
        session.add(
            Document(
                document_id=document_id,
                project_id=project_id,
                filename=f"{label}.md",
                media_type="text/markdown",
                content_text=f"{label} evidence",
            )
        )
        session.flush()
        session.add(
            DocumentChunk(
                chunk_id=uuid4(),
                document_id=document_id,
                chunk_index=0,
                content=f"{label} evidence",
                embedding=QUERY_VECTOR,
            )
        )
    return project_id


def test_agent_run_context_isolates_project_knowledge():
    owner_user_id = uuid4()
    project_a = add_project_chunk(owner_user_id, "project-a")
    project_b = add_project_chunk(owner_user_id, "project-b")
    backend = TestClient(app)
    app.dependency_overrides[get_embedding_factory] = lambda: FakeEmbeddings
    writer = RecordingWriter()

    def backend_post(url, **kwargs):
        assert kwargs.pop("timeout") == KNOWLEDGE_TIMEOUT_SECONDS
        return backend.post(url, **kwargs)

    graph = build_graph(
        researcher_model=FakeResearcherModel(),
        web_tool=UnusedWebTool(),
        knowledge_client=KnowledgeClient(
            "http://backend.test",
            post=backend_post,
        ),
        writer_impl=writer,
        # One round is enough: this test is about context isolation, and the fake
        # model repeats the same tool call on every turn.
        max_tool_rounds=1,
    )

    try:
        for project_id in (project_a, project_b):
            graph.invoke(
                {"messages": [HumanMessage(content="research")]},
                context=AgentContext(
                    knowledge_scope=KnowledgeScope(
                        user_id=owner_user_id,
                        project_id=project_id,
                    )
                ),
            )
    finally:
        app.dependency_overrides.pop(get_embedding_factory, None)

    assert [
        [item["content"] for item in payload["evidence"]]
        for payload in writer.payloads
    ] == [["project-a evidence"], ["project-b evidence"]]
