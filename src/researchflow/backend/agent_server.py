import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

import httpx
from langgraph_sdk import get_sync_client

# The SDK builds its own transport with `retries=5`, so its timeout is a *per
# attempt* budget: a stopped container multiplies it into ~31 seconds of silence
# before the request fails. A call-level deadline is the only way to bound what
# the user experiences.
AGENT_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
AGENT_CALL_TIMEOUT_SECONDS = 12.0


class AgentServerTimeout(RuntimeError):
    """The Agent Server did not answer within the deadline."""


class AgentServerClient:
    def __init__(
        self,
        *,
        url: str,
        graph_id: str,
        call_timeout: float = AGENT_CALL_TIMEOUT_SECONDS,
    ):
        self._graph_id = graph_id
        self._call_timeout = call_timeout
        self._client = get_sync_client(url=url, timeout=AGENT_TIMEOUT)
        # Reused so a failing call does not spawn a thread per attempt. A call
        # that exceeds the deadline keeps its thread until the SDK gives up, so
        # the pool bounds how many such stragglers can exist at once.
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="agent-call"
        )

    def _call(self, function, *args, **kwargs):
        future = self._executor.submit(function, *args, **kwargs)
        try:
            return future.result(timeout=self._call_timeout)
        except FutureTimeout:
            raise AgentServerTimeout(
                f"Agent Server did not answer within {self._call_timeout:.0f}s"
            ) from None

    def create_thread(self, *, project_id: str, research_session_id: str) -> str:
        thread = self._call(
            self._client.threads.create,
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
        self._call(self._client.threads.delete, thread_id)

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        return self._call(self._client.threads.get, thread_id)


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
