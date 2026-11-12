"""The Agent Server client must fail fast when the server does not answer."""

import time

import httpx
import pytest

from researchflow.backend import agent_server
from researchflow.backend.agent_server import (
    AGENT_TIMEOUT,
    AgentServerClient,
    AgentServerTimeout,
)


class FakeThreads:
    def __init__(self, *, delay: float = 0.0, error: Exception | None = None, thread=None):
        self.delay = delay
        self.error = error
        self.thread = thread if thread is not None else {"thread_id": "thread-1"}
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.thread


@pytest.fixture
def stub_client(monkeypatch):
    """Replace the SDK client so no request leaves the process."""

    captured: dict = {}

    def install(threads: FakeThreads):
        class Client:
            pass

        client = Client()
        client.threads = threads

        def fake_get_sync_client(**kwargs):
            captured.update(kwargs)
            return client

        monkeypatch.setattr(agent_server, "get_sync_client", fake_get_sync_client)
        return captured

    return install


def build(threads: FakeThreads, *, call_timeout: float = 12.0) -> AgentServerClient:
    return AgentServerClient(
        url="http://agent.test",
        graph_id="researchflow",
        call_timeout=call_timeout,
    )


def test_the_sdk_client_carries_an_httpx_timeout(stub_client):
    captured = stub_client(FakeThreads())

    build(FakeThreads())

    assert captured["url"] == "http://agent.test"
    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect is not None and timeout.connect <= 5


def test_create_thread_returns_the_id(stub_client):
    threads = FakeThreads()
    stub_client(threads)

    client = build(threads)

    assert client.create_thread(project_id="p", research_session_id="s") == "thread-1"
    assert threads.calls[0]["graph_id"] == "researchflow"
    assert threads.calls[0]["metadata"] == {
        "project_id": "p",
        "research_session_id": "s",
    }


def test_a_hung_call_raises_at_the_deadline_instead_of_the_sdk_timeout(stub_client):
    """The SDK retries five times, so its budget is ~31s; ours is what the user sees."""

    threads = FakeThreads(delay=3.0)
    stub_client(threads)
    client = build(threads, call_timeout=0.3)

    started = time.monotonic()
    with pytest.raises(AgentServerTimeout):
        client.create_thread(project_id="p", research_session_id="s")

    assert time.monotonic() - started < 2.0


def test_a_transport_error_still_propagates(stub_client):
    stub_client(FakeThreads(error=httpx.ConnectError("refused")))

    with pytest.raises(httpx.ConnectError):
        build(FakeThreads()).create_thread(project_id="p", research_session_id="s")


def test_an_invalid_thread_id_is_rejected(stub_client):
    stub_client(FakeThreads(thread={"thread_id": ""}))

    with pytest.raises(RuntimeError, match="invalid thread_id"):
        build(FakeThreads()).create_thread(project_id="p", research_session_id="s")
