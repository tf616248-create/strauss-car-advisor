"""Scope eval against the real model (needs keys in backend/.env).

    cd backend
    python -m evals.run_off_topic             # both sets
    python -m evals.run_off_topic in_scope    # one set

Off topic (off_topic.json): passes when the answer contains the fixed out-of-scope sentence
and no tool was called. In scope (in_scope.json): passes when Kobi really answers - no fixed
sentence (tools are fine there). Each case runs in its own conversation.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from langchain_core.messages import AIMessage

BACKEND_DIR = Path(__file__).resolve().parents[1]
CASES_FILE = BACKEND_DIR / "evals" / "off_topic.json"
IN_SCOPE_FILE = BACKEND_DIR / "evals" / "in_scope.json"


def _final_text(messages: list) -> str:
    final = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    return (final.text if final is not None else "") or ""  # .text joins the text parts (some models return a list)


def judge(messages: list, sentence: str) -> tuple[bool, str]:
    """Off topic: (passed, why not). Looks at the whole turn: any tool call fails it."""
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            return False, "called " + ", ".join(tc["name"] for tc in m.tool_calls)
    if sentence not in _final_text(messages):
        return False, "no fixed sentence"
    return True, ""


def judge_in_scope(messages: list, sentence: str) -> tuple[bool, str]:
    """In scope: (passed, why not). A real answer, not the refusal."""
    text = _final_text(messages)
    if not text.strip():
        return False, "empty answer"
    if sentence in text:
        return False, "refused (fixed sentence)"
    return True, ""


def main() -> None:
    from dotenv import load_dotenv

    from app.agent.advisor import load_agent_config
    from app.agent.graph import build_agent
    from app.agent.models import build_model
    from app.agent.rep_queue import InMemoryRepQueue
    from app.data.loader import load_all

    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BACKEND_DIR / ".env")
    cfg = load_agent_config(BACKEND_DIR)
    sentence = cfg["texts"]["outOfScope"]
    agent = build_agent(build_model(cfg["modelTimeoutSeconds"], thinking_level=cfg["geminiThinkingLevel"]),
                        load_all(BACKEND_DIR), InMemoryRepQueue(), cfg)
    sets = {"off_topic": ("off topic", CASES_FILE, judge), "in_scope": ("in scope", IN_SCOPE_FILE, judge_in_scope)}
    chosen = sys.argv[1:] or list(sets)  # e.g. "python -m evals.run_off_topic in_scope" saves model quota
    for title, path, check in (sets[name] for name in chosen):
        cases = json.loads(path.read_text(encoding="utf-8"))
        passed = 0
        print(f"\n== {title} ==")
        for case in cases:
            config = {"configurable": {"thread_id": f"eval-{uuid.uuid4()}"}}
            try:
                out = agent.invoke({"messages": [("user", case["question"])]}, config)
                ok, why = check(out["messages"], sentence)
                answer = _final_text(out["messages"])
            except Exception as e:  # e.g. every model failed: counts as a fail, with the reason
                ok, why, answer = False, f"error: {type(e).__name__}: {e}", ""
            passed += ok
            print(f'{"PASS" if ok else "FAIL"}  [{case["kind"]}] {case["id"]}: {case["question"]}')
            if not ok:
                print(f"      why: {why}\n      answer: {answer[:300]}")
        print(f"{title}: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
