import os
from typing import Any

from langgraph_sdk import get_sync_client


class AgentServerClient:
    def __init__(self, *, url: str, graph_id: str):
        self._graph_id = graph_id
        self._client = get_sync_client(url=url)

    def create_thread(self, *, project_id: str, research_session_id: str) -> str:
        thread = self._client.threads.create(
            graph_id=self._graph_id,
            metadata={
                "project_id": project_id,
                "research_session_id": research_session_id,
            },
        )
        thread_id = thread["thread_id"]
        if not isinstance(thread_id, str) or not thread_id:
            raise RuntimeError("Agent server returned an invalid thread_id")
        return thread_id

    def delete_thread(self, thread_id: str) -> None:
        self._client.threads.delete(thread_id)

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        return self._client.threads.get(thread_id)


def require_agent_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_agent_server() -> AgentServerClient:
    return AgentServerClient(
        url=require_agent_setting("RESEARCHFLOW_LANGGRAPH_URL"),
        graph_id=require_agent_setting("RESEARCHFLOW_GRAPH_ID"),
    )
