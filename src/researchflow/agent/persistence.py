"""Persist a finished research run to the Product Backend.

Graph State lives in the LangGraph checkpoint, which the local development server
keeps in memory: a restart loses every report even though PostgreSQL still holds
the session row. This module is the durable write.

Failure policy: persistence never fails a run. The report already exists at this
point, so a backend outage is logged and the run still returns its result. The
cost of a lost write is a missing history row, not a lost answer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

PERSIST_TIMEOUT_SECONDS = 15.0


class ReportPersister:
    """Writes a report to ``POST .../research-sessions/{id}/reports``."""

    def __init__(
        self,
        base_url: str,
        *,
        post: Callable[..., httpx.Response] = httpx.post,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise ValueError("Backend URL cannot be empty")
        self._base_url = normalized
        self._post = post

    def save(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        research_session_id: UUID,
        report: str,
        citations: list[dict[str, Any]],
        verification: list[dict[str, Any]],
        tool_rounds: int,
    ) -> str | None:
        """Return the created report id, or None when the write was rejected."""

        response = self._post(
            f"{self._base_url}/projects/{project_id}/research-sessions/"
            f"{research_session_id}/reports",
            headers={"X-ResearchFlow-User-Id": str(user_id)},
            json={
                "report": report,
                "citations": citations,
                "verification": verification,
                "tool_rounds": tool_rounds,
            },
            timeout=PERSIST_TIMEOUT_SECONDS,
        )
        if response.status_code != 201:
            return None
        payload = response.json()
        report_id = payload.get("report_id") if isinstance(payload, dict) else None
        return report_id if isinstance(report_id, str) else None
