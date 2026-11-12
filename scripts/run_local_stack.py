"""Run the Product Backend or the Agent Server as local processes.

The Compose stack is the one-command path, but building its image needs a
reachable container registry. When that is not available (an offline network, a
blocked registry, a proxy that is not running) these two processes are enough to
run the whole product against a local PostgreSQL.

Usage::

    py -3.12 -m scripts.run_local_stack postgres   # prints the compose command
    py -3.12 -m scripts.run_local_stack backend
    py -3.12 -m scripts.run_local_stack agent
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load .env the same way the Agent Server does, without overwriting."""

    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("postgres", "backend", "agent"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--agent-port", type=int, default=2024)
    args = parser.parse_args(argv)

    load_env()
    os.environ.setdefault(
        "RESEARCHFLOW_DATABASE_URL",
        "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow",
    )

    if args.service == "postgres":
        print("docker compose up -d postgres")
        return 0

    if args.service == "backend":
        import uvicorn

        uvicorn.run(
            "researchflow.backend.app:app",
            host=args.host,
            port=args.backend_port,
            log_level="warning",
        )
        return 0

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "langgraph_cli",
            "dev",
            "--host",
            args.host,
            "--port",
            str(args.agent_port),
            "--no-browser",
            "--allow-blocking",
            # A reload clears the in-memory thread store and orphans live sessions.
            "--no-reload",
        ],
        cwd=ROOT,
        env=os.environ,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
