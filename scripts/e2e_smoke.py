"""End-to-end smoke test through the real product path.

Creates a Project, provisions a Research Session (which asks the Agent Server for
a LangGraph thread), uploads two evaluation documents, submits a run through the
Agent Server exactly as the Frontend does, and reads the persisted report back.

This is the check that proves the three services agree with each other. It needs
the stack to be running, so it is a script rather than a test.

Usage::

    py -3.12 -m scripts.e2e_smoke
    py -3.12 -m scripts.e2e_smoke --keep    # leave the Project behind for inspection
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "evaluations" / "datasets" / "retrieval_v4.json"

QUESTION = (
    "What does arc.digits() return by default, and which option changes it? "
    "Cite the documentation."
)


class Smoke:
    def __init__(self, backend: str, user_id: str) -> None:
        self.backend = backend.rstrip("/")
        self.user_id = user_id
        self.failures = 0

    def call(self, method: str, path: str, *, body=None, files=None, timeout=240):
        headers = {"X-ResearchFlow-User-Id": self.user_id}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if files is not None:
            boundary = uuid.uuid4().hex
            name, content = files
            data = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
                "Content-Type: text/markdown\r\n\r\n"
            ).encode() + content.encode() + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = urllib.request.Request(
            f"{self.backend}{path}", data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                return response.status, json.loads(payload) if payload else None
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")[:300]

    def check(self, label: str, status: int, expected: int) -> object:
        ok = status == expected
        print(f"{'OK  ' if ok else 'FAIL'} {label}: {status}")
        if not ok:
            self.failures += 1
        return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--agent", default="http://127.0.0.1:2024")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    smoke = Smoke(args.backend, str(uuid.uuid4()))

    status, project = smoke.call("POST", "/projects", body={"name": "e2e-smoke"})
    if not smoke.check("create project", status, 201):
        return 1
    project_id = project["project_id"]

    # This call only succeeds when the Agent Server is reachable.
    status, session = smoke.call("POST", f"/projects/{project_id}/research-sessions")
    if not smoke.check("provision research session (agent server reachable)", status, 201):
        return 1
    session_id = session["research_session_id"]
    thread_id = session["thread_id"]

    dataset = json.loads(DATASET.read_text(encoding="utf-8-sig"))
    visual = next(p for p in dataset["projects"] if p["project_key"] == "data-visualisation")
    for document in visual["documents"][:2]:
        status, _ = smoke.call(
            "POST",
            f"/projects/{project_id}/documents",
            files=(document["filename"], document["content"]),
        )
        if not smoke.check(f"upload {document['filename']}", status, 201):
            return 1

    from langgraph_sdk import get_sync_client

    client = get_sync_client(url=args.agent)
    if client.threads.get(thread_id)["thread_id"] != thread_id:
        print("FAIL thread is missing on the agent server")
        return 1
    print(f"OK   thread {thread_id[:8]} exists on the agent server")

    started = time.time()
    run = client.runs.create(
        thread_id,
        "researchflow",
        input={"messages": [{"role": "user", "content": QUESTION}]},
        context={
            "knowledge_scope": {"user_id": smoke.user_id, "project_id": project_id},
            "research_session_id": session_id,
        },
    )
    print(f"OK   run {run['run_id'][:8]} created")

    final = None
    for _ in range(300):
        state = client.runs.get(thread_id, run["run_id"])
        if state["status"] in {"success", "error", "interrupted"}:
            final = state
            break
        time.sleep(2)

    if final is None:
        print("FAIL run did not finish within 10 minutes")
        return 1
    if final["status"] != "success":
        print(f"FAIL run ended as {final['status']}")
        return 1

    elapsed = round(time.time() - started, 1)
    values = client.threads.get_state(thread_id)["values"]
    report = values.get("report") or ""
    citations = values.get("citations") or []
    print(
        f"OK   run finished in {elapsed}s: report {len(report)} chars, "
        f"{len(citations)} citations, {values.get('tool_rounds')} rounds"
    )
    if not report.strip():
        print("FAIL the run produced no report")
        return 1
    if "[c" not in report:
        print("FAIL the report cites nothing")
        return 1

    status, reports = smoke.call(
        "GET", f"/projects/{project_id}/research-sessions/{session_id}/reports"
    )
    if not smoke.check("read persisted reports", status, 200):
        return 1
    if not reports:
        print("FAIL the run was not persisted")
        return 1

    latest = reports[0]
    print(
        f"OK   stored report {latest['report_id'][:8]}: {len(latest['report'])} chars, "
        f"{len(latest['citations'])} citations, {len(latest['verification'])} verdicts"
    )
    if latest["report"].strip() != report.strip():
        print("FAIL the stored report does not match the thread state")
        return 1
    print("OK   stored report matches the thread state")

    if args.keep:
        print(f"     kept project {project_id}")
    else:
        status, _ = smoke.call("DELETE", f"/projects/{project_id}")
        smoke.check("cleanup", status, 204)

    if smoke.failures:
        print(f"\n{smoke.failures} check(s) failed")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
