"""The weekly usage limit per employee, in tokens (config/agent.json "usage").

- What counts: every billed token of the employee's questions - input and output, of whichever model
  answered (the fallbacks too), and the payslip's reading. A call that failed has no usage, so it adds
  nothing. A run tagged "eval" (evals/run_off_topic.py) never counts.
- The week starts on Sunday at 00:00, Israel time (usage.timezone). A new week is a new row, so the
  reset needs no job.
- At 0 the server answers with the fixed message (texts.usage.limitReached) and calls no model. It is
  checked before each employee message; an answer that already started runs to its end, and is counted
  after it, so the block applies from the next message.
InMemoryUsage here; app/db.py has PostgresUsage (table employee_usage) behind the same methods.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage


def week_start(now: datetime, tz: str) -> date:
    """The Sunday that starts this week, at 00:00 in tz (Asia/Jerusalem: summer and winter time alike)."""
    local = now.astimezone(ZoneInfo(tz))
    return (local - timedelta(days=(local.weekday() + 1) % 7)).date()  # Monday=0 ... Sunday=6


def tokens_of(messages: Iterable) -> int:
    """The billed tokens of these model messages: input + output (thinking included in output)."""
    total = 0
    for m in messages:
        if isinstance(m, AIMessage) and m.usage_metadata:
            total += m.usage_metadata.get("input_tokens", 0) + m.usage_metadata.get("output_tokens", 0)
    return total


class InMemoryUsage:
    def __init__(self):
        self._rows: dict[tuple[str, date], int] = {}

    def used(self, employee_id: str, week: date) -> int:
        return self._rows.get((employee_id, week), 0)

    def add(self, employee_id: str, week: date, tokens: int) -> None:
        self._rows[(employee_id, week)] = self.used(employee_id, week) + tokens


class UsageMeter:
    def __init__(self, store, cfg: dict, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.store = store
        self.u = cfg["usage"]
        self.now = now

    def _week(self) -> date:
        return week_start(self.now(), self.u["timezone"])

    def record(self, employee_id: Optional[str], messages: Iterable, config: Optional[dict] = None) -> int:
        """Adds the question's billed tokens to this week. An eval run (tag "eval") is not counted."""
        if not employee_id or "eval" in ((config or {}).get("tags") or []):
            return 0
        tokens = tokens_of(messages)
        if tokens:
            self.store.add(employee_id, self._week(), tokens)
        return tokens

    def status(self, employee_id: str) -> dict:
        week = self._week()
        limit, avg = self.u["weekly_token_limit"], self.u["avg_tokens_per_conversation"]
        used = self.store.used(employee_id, week)
        remaining = max(0, limit - used)
        return {"used": used, "limit": limit, "remaining": remaining, "avg_tokens_per_conversation": avg,
                "conversations_left": remaining // avg, "blocked": remaining <= 0,
                "resets_on": (week + timedelta(days=7)).isoformat()}

    def blocked(self, employee_id: Optional[str]) -> bool:
        return bool(employee_id) and self.status(employee_id)["blocked"]
