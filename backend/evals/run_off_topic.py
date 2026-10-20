"""Scope eval against the real model (needs keys in backend/.env).

    cd backend
    python -m evals.run_off_topic             # both sets
    python -m evals.run_off_topic in_scope    # one set

Off topic (off_topic.json): passes when the answer contains the fixed out-of-scope sentence
and no tool was called. In scope (in_scope.json): passes when Kobi really answers - no fixed
sentence (tools are fine there). Recommend (recommend.json): each case says what it expects
("expect": tools called or not, their arguments, words in the answer) - judge_expect reads it.
Each case runs in its own conversation.

    python -m evals.run_off_topic recommend
    python -m evals.run_off_topic recommend family-safe roomy-safe   # only these cases

Recalc (recalc.json): two questions in one conversation - the employee corrects a detail or
switches car - and the last one is judged like recommend: calculate has to run again.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

BACKEND_DIR = Path(__file__).resolve().parents[1]
CASES_FILE = BACKEND_DIR / "evals" / "off_topic.json"
IN_SCOPE_FILE = BACKEND_DIR / "evals" / "in_scope.json"
RECOMMEND_FILE = BACKEND_DIR / "evals" / "recommend.json"
RECALC_FILE = BACKEND_DIR / "evals" / "recalc.json"


def questions_of(case: dict) -> list[str]:
    """The case's questions, asked in order in one conversation."""
    return case.get("turns") or [case["question"]]


def last_turn(messages: list) -> list:
    """The messages from the last employee question on: a recalc is judged on that turn only."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    return messages[starts[-1]:] if starts else messages


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


def judge_expect(messages: list, expect: dict, sentence: str, car_names: list[str]) -> tuple[bool, str]:
    """Recommend: (passed, why not), from the case's "expect"."""
    calls = [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
    called = {tc["name"] for tc in calls}
    text = _final_text(messages)
    for name in expect.get("no_tools", []):
        if name in called:
            return False, f"called {name}"
    for name in expect.get("tools", []):
        if name not in called:
            return False, f"did not call {name}"
    for name, wanted in expect.get("tool_args", {}).items():
        if not any(tc["name"] == name and all(tc["args"].get(k) == v for k, v in wanted.items()) for tc in calls):
            return False, f"{name} without {wanted}"
    for name, keys in expect.get("tool_args_any", {}).items():
        if not any(tc["name"] == name and any(tc["args"].get(k) not in (None, [], "") for k in keys) for tc in calls):
            return False, f"{name} without any of {keys}"
    if expect.get("not_refused") and sentence in text:
        return False, "refused (fixed sentence)"
    if expect.get("no_car_names"):
        shown = [n for n in car_names if n.upper() in text.upper()]
        if shown:
            return False, "shows cars before rank_options: " + ", ".join(shown)
    for group in expect.get("text_any", []):
        if not any(word in text for word in group):
            return False, f"answer has none of {group}"
    return True, ""


def main() -> None:
    from dotenv import load_dotenv

    from app.agent.advisor import load_agent_config
    from app.agent.graph import build_agent
    from app.agent.models import ModelStalledError, build_model
    from app.agent.rep_queue import InMemoryRepQueue
    from app.data.loader import load_all

    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BACKEND_DIR / ".env")
    cfg = load_agent_config(BACKEND_DIR)
    sentence = cfg["texts"]["outOfScope"]
    data = load_all(BACKEND_DIR)
    agent = build_agent(build_model(cfg["modelTimeoutSeconds"], thinking_level=cfg["geminiThinkingLevel"]),
                        data, InMemoryRepQueue(), cfg)  # car specs: the snapshot in git
    cars = [c["name"] for c in data.catalog.values()]
    sets = {"off_topic": ("off topic", CASES_FILE, lambda m, s, case: judge(m, s)),
            "in_scope": ("in scope", IN_SCOPE_FILE, lambda m, s, case: judge_in_scope(m, s)),
            "recommend": ("recommend", RECOMMEND_FILE, lambda m, s, case: judge_expect(m, case["expect"], s, cars)),
            "recalc": ("recalc", RECALC_FILE, lambda m, s, case: judge_expect(m, case["expect"], s, cars))}
    names = [a for a in sys.argv[1:] if a in sets]
    only = [a for a in sys.argv[1:] if a not in sets]  # case ids: run just these, saves model quota
    for title, path, check in (sets[name] for name in names or list(sets)):
        cases = [c for c in json.loads(path.read_text(encoding="utf-8")) if not only or c["id"] in only]
        passed = 0
        print(f"\n== {title} ==")
        for case in cases:
            config = {"configurable": {"thread_id": f"eval-{uuid.uuid4()}"}}
            try:
                for question in questions_of(case):
                    out = agent.invoke({"messages": [("user", question)]}, config)
                ok, why = check(last_turn(out["messages"]), sentence, case)
                answer = _final_text(out["messages"])
            except (Exception, ModelStalledError) as e:  # e.g. every model failed: counts as a fail, with the reason
                ok, why, answer = False, f"error: {type(e).__name__}: {e}", ""
            passed += ok
            print(f'{"PASS" if ok else "FAIL"}  [{case.get("kind", title)}] {case["id"]}: {questions_of(case)[-1]}')
            if not ok:
                print(f"      why: {why}\n      answer: {answer[:300]}")
        print(f"{title}: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
