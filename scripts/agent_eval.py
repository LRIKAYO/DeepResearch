"""Agent-level evaluation: run the real graph and aggregate its own quality signals.

The retrieval evaluation scores chunks. This one scores the *agent*: how many tool
rounds it spends, whether the report cites every source it lists, what the
verifier says about each citation, and how long the run takes.

It needs a running Product Backend (for knowledge_search) and real provider
credentials, so it is a script rather than a test. It ingests two volumes of the
evaluation corpus into a fresh Project, asks a small fixed question set, and
writes a JSON + Markdown report.

Usage::

    py -3.12 -m scripts.agent_eval --out evaluations/reports/agent-eval.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET = PROJECT_ROOT / "evaluations" / "datasets" / "retrieval_v4.json"

QUESTIONS = [
    (
        "arc-default-digits",
        "What does arc.digits() return when no argument is given, and what option "
        "changes the number of decimal places?",
        "en",
    ),
    (
        "d3-natural-sort",
        "Why can the default numeric sort of d3-array be unsafe, and what does the "
        "natural-order comparator return for null?",
        "en",
    ),
    (
        "d3-array-zip",
        "d3.zip 在参数长度不一致时会返回什么？返回数组的长度由谁决定？",
        "zh",
    ),
    (
        "unsupported-pricing",
        "How much does the d3-shape commercial licence cost per year and what support "
        "SLA does it include?",
        "en",
    ),
]


def call(method: str, path: str, *, user_id: str, body=None, files=None):
    url = f"{BASE}{path}"
    headers = {"X-ResearchFlow-User-Id": user_id}
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
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:400]


BASE = "http://127.0.0.1:8000"


def main(argv: list[str] | None = None) -> int:
    global BASE

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)

    BASE = args.api

    for line in args.env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

    from langchain_core.messages import HumanMessage

    from researchflow.agent.citation_audit import (
        audit_citations,
        citation_ids_for,
        unmarked_claim_sentences,
    )
    from researchflow.agent.runtime import create_runtime

    user_id = str(uuid.uuid4())
    status, project = call("POST", "/projects", user_id=user_id, body={"name": "agent-eval"})
    if status != 201:
        raise SystemExit(f"cannot create project: {status} {project}")
    project_id = project["project_id"]

    dataset = json.loads(DATASET.read_text(encoding="utf-8-sig"))
    visual = next(p for p in dataset["projects"] if p["project_key"] == "data-visualisation")
    uploaded = 0
    for document in visual["documents"][:3]:
        status, _ = call(
            "POST",
            f"/projects/{project_id}/documents",
            user_id=user_id,
            files=(document["filename"], document["content"].encode("utf-8")),
        )
        if status != 201:
            raise SystemExit(f"cannot upload {document['filename']}: {status}")
        uploaded += 1
    print(f"project {project_id[:8]} with {uploaded} documents")

    graph = create_runtime()
    rows = []

    for case_id, question, language in QUESTIONS:
        started = time.time()
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=question)]},
                context={"knowledge_scope": {"user_id": user_id, "project_id": project_id}},
                config={"configurable": {"thread_id": f"agent-eval-{case_id}"}},
            )
            error = None
        except Exception as exc:  # a failed run is a data point, not a crash
            result, error = {}, f"{type(exc).__name__}: {exc}"
        elapsed = time.time() - started

        report = result.get("report") or ""
        citations = result.get("citations") or []
        audit = audit_citations(report, citation_ids_for(len(citations)))
        verdicts = result.get("verification") or []
        support: dict[str, int] = {}
        for verdict in verdicts:
            support[verdict["support"]] = support.get(verdict["support"], 0) + 1

        row = {
            "case_id": case_id,
            "language": language,
            "elapsed_seconds": round(elapsed, 1),
            "error": error,
            "tool_rounds": result.get("tool_rounds"),
            "sub_questions": len(result.get("sub_questions") or []),
            "citations": len(citations),
            "citation_coverage": round(audit.coverage, 3),
            "uncited_ids": len(audit.uncited),
            "unmarked_claims": len(unmarked_claim_sentences(report)),
            "verification": support,
            "report_chars": len(report),
            "report_head": report[:300],
        }
        rows.append(row)
        print(
            f"  {case_id:<22} rounds={row['tool_rounds']} citations={row['citations']} "
            f"coverage={row['citation_coverage']} support={support} "
            f"{row['elapsed_seconds']}s"
            + (f" ERROR {error}" if error else "")
        )

    failures = [row for row in rows if row["error"]]
    total_citations = sum(row["citations"] for row in rows)
    supported = sum(row["verification"].get("full", 0) for row in rows)
    partial = sum(row["verification"].get("partial", 0) for row in rows)
    unsupported = sum(row["verification"].get("none", 0) for row in rows)

    summary = {
        "questions": len(rows),
        "failures": len(failures),
        "tool_rounds_total": sum(row["tool_rounds"] or 0 for row in rows),
        "tool_rounds_mean": round(
            sum(row["tool_rounds"] or 0 for row in rows) / max(len(rows), 1), 2
        ),
        "citations_total": total_citations,
        "citation_coverage_mean": round(
            sum(row["citation_coverage"] for row in rows) / max(len(rows), 1), 3
        ),
        "verdicts": {"full": supported, "partial": partial, "none": unsupported},
        "support_rate": round(supported / total_citations, 3) if total_citations else None,
        "latency_p50_seconds": sorted(row["elapsed_seconds"] for row in rows)[
            len(rows) // 2
        ],
    }

    print()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"summary": summary, "cases": rows}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print("wrote", args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
