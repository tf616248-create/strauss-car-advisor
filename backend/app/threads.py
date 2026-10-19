"""Whose conversation is it, and each employee's history list.

The conversation itself (messages, cards) stays in LangGraph's checkpointer; this only keeps
(employee, thread, title, updated_at). In memory for tests and local development; app/db.py has
the Postgres (Neon) version behind the same methods (tests/test_threads_repository.py runs on both).
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Optional


class InMemoryThreads:
    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._order = itertools.count()  # ties in the clock still sort by the last change

    def _stamp(self, row: dict) -> None:
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        row["seq"] = next(self._order)

    def add(self, employee_id: str, thread_id: str) -> None:
        """A new conversation for this employee. A second add keeps the first owner."""
        if thread_id not in self._rows:
            row = {"employee_id": employee_id, "thread_id": thread_id, "title": None}
            self._stamp(row)
            self._rows[thread_id] = row

    def owner(self, thread_id: str) -> Optional[str]:
        row = self._rows.get(thread_id)
        return row["employee_id"] if row else None

    def touch(self, thread_id: str, title: Optional[str]) -> None:
        """After each answer: the title (from the conversation) and to the top of the list."""
        row = self._rows.get(thread_id)
        if row:
            row["title"] = title
            self._stamp(row)

    def list(self, employee_id: str, limit: int = 50) -> list[dict]:
        rows = sorted((r for r in self._rows.values() if r["employee_id"] == employee_id),
                      key=lambda r: r["seq"], reverse=True)
        return [{"thread_id": r["thread_id"], "title": r["title"], "updated_at": r["updated_at"]}
                for r in rows[:limit]]
