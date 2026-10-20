"""LangSmith tracing - switched on only by the environment, never by a key in code.

    LANGSMITH_TRACING=true, LANGSMITH_API_KEY=<key>, LANGSMITH_PROJECT=<project name, optional>

Both of the first two, or tracing is off: nothing is sent and everything else works the same (no error).
Tracing on without a key is switched off with a log line, instead of failing to send in the background.

Every run carries the conversation id (metadata "thread_id": LangSmith shows a conversation's traces
together); each model call carries the model that answered and whether it was a fallback (app/agent/
models.py); an eval run is tagged "eval", with its set and case (evals/run_off_topic.py).

Note: a trace holds the whole conversation, salary details included. Only demo data while it is on.
"""
from __future__ import annotations

import logging
from typing import Mapping

import langsmith

log = logging.getLogger("app.tracing")


def configure(env: Mapping[str, str]) -> bool:
    """Turns tracing on or off for the whole process, from these variables. Returns whether it is on."""
    wanted = env.get("LANGSMITH_TRACING", "").strip().lower() == "true"
    on = wanted and bool(env.get("LANGSMITH_API_KEY"))
    if wanted and not on:
        log.warning("LangSmith: LANGSMITH_TRACING is on but LANGSMITH_API_KEY is empty - tracing stays off")
    # enabled=False also beats older variables (LANGCHAIN_TRACING_V2) that might be lying around
    langsmith.configure(enabled=on, project_name=(env.get("LANGSMITH_PROJECT") or None) if on else None)
    if on:
        log.info("LangSmith: tracing on (project %s)", env.get("LANGSMITH_PROJECT") or "default")
    return on


def eval_config(thread_id: str, eval_set: str, case_id: str) -> dict:
    """The run config of an eval conversation: tagged "eval", with its set and case."""
    return {"configurable": {"thread_id": thread_id}, "tags": ["eval"],
            "metadata": {"thread_id": thread_id, "eval_set": eval_set, "eval_case": case_id}}
