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

Main flow (main_flow.json): the PDF demo, a group x option matrix of net questions, missing details,
the rep after two failed attempts, prompt injection, and the employee profile (a case's "profile" is
put in a profile store for a throwaway employee) - judged by judge_main, in code only (no LLM
judge): which tools ran and with what, the net in the answer equals what calculate gives for the
case's details, no number the tools or the employee did not give, no forbidden phrase.

Every run writes a table of pass/fail with the reason to evals/results/<sets>-<date>.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

BACKEND_DIR = Path(__file__).resolve().parents[1]
CASES_FILE = BACKEND_DIR / "evals" / "off_topic.json"
IN_SCOPE_FILE = BACKEND_DIR / "evals" / "in_scope.json"
RECOMMEND_FILE = BACKEND_DIR / "evals" / "recommend.json"
RECALC_FILE = BACKEND_DIR / "evals" / "recalc.json"
MAIN_FLOW_FILE = BACKEND_DIR / "evals" / "main_flow.json"
RESULTS_DIR = BACKEND_DIR / "evals" / "results"

# never in an answer: the bot compares and does not recommend in Strauss's name, and never sends the
# employee to the rep (it asks the rep itself)
FORBIDDEN = ["שטראוס ממליצה", "פנה לנציג", "פני לנציג", "פנו לנציג"]  # also catches "תפנה לנציג"
# smaller numbers (percentages, children, ages, credit points) are not checked against the tools
MIN_CHECKED_NUMBER = 100


def questions_of(case: dict) -> list[str]:
    """The case's questions, asked in order in one conversation."""
    return case.get("turns") or [case["question"]]


def last_turn(messages: list) -> list:
    """The messages from the last employee question on: a recalc is judged on that turn only."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    return messages[starts[-1]:] if starts else messages


def turns_of(messages: list) -> list[list]:
    """The conversation split by employee question."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)] or [0]
    return [messages[a:b] for a, b in zip(starts, starts[1:] + [len(messages)])]


def numbers_in(text: str) -> set[float]:
    """Every number in a text, without sign or thousands commas: "-1,153" -> 1153."""
    return {float(n.replace(",", "")) for n in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)}


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


def _calls(messages: list) -> list[dict]:
    return [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]


def _results_of(messages: list, name: str) -> list[dict]:
    out = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == name:
            try:
                out.append(json.loads(m.content))
            except (TypeError, ValueError):
                pass
    return out


def judge_main(messages: list, case: dict, sentence: str, car_names: list[str],
               expected_net: Callable[[dict], Optional[float]]) -> tuple[bool, str]:
    """Main flow: (passed, why not), in code only. messages: the whole conversation.

    expected_net(args): the net difference calculate gives for these details (run without a model).
    """
    expect = case["expect"]
    scope = messages if case.get("judge_on") == "conversation" else last_turn(messages)
    text = _final_text(messages)
    if "first_turn" in expect:
        ok, why = judge_main(turns_of(messages)[0], {"expect": expect["first_turn"]}, sentence, car_names,
                             expected_net)
        if not ok:
            return False, "first turn: " + why
    for phrase in FORBIDDEN + expect.get("text_none", []):
        if phrase in text:
            return False, f'answer says "{phrase}"'
    if expect.get("refused"):
        ok, why = judge(scope, sentence)
        if not ok:
            return False, why
    ok, why = judge_expect(scope, expect, sentence, car_names)
    if not ok:
        return False, why
    for name, fields in expect.get("args_absent", {}).items():
        for tc in _calls(scope):
            guessed = [f for f in fields if tc["name"] == name and tc["args"].get(f) not in (None, "")]
            if guessed:
                return False, f"{name} guessed {guessed}"
    for name in expect.get("not_ok", []):  # e.g. calculate before the missing details were given
        if any(r.get("status") == "ok" for r in _results_of(scope, name)):
            return False, f"{name} gave a result (status ok)"
    if "net_from_calculate" in expect:
        want = expected_net(expect["net_from_calculate"])
        got = [r["card"]["diff"]["net"] for r in _results_of(scope, "calculate") if r.get("status") == "ok"]
        if not got:
            return False, "no calculate result with status ok"
        if got[-1] != want:
            return False, f"calculate gave {got[-1]:,}, expected {want:,} (other details passed to the tool)"
        if abs(want) not in numbers_in(text):
            return False, f"answer does not show the net difference {abs(want):,}"
    if expect.get("numbers_from_tools"):
        given = set()
        for m in messages:
            if isinstance(m, (ToolMessage, HumanMessage)):
                given |= numbers_in(m.content if isinstance(m.content, str) else json.dumps(m.content))
        invented = sorted(n for n in numbers_in(text) if n >= MIN_CHECKED_NUMBER and n not in given)
        if invented:
            return False, "numbers not from a tool or the employee: " + ", ".join(f"{n:g}" for n in invented)
    return True, ""


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def results_markdown(rows: list[dict], when: str) -> str:
    passed = sum(r["ok"] for r in rows)
    costs = [r["cost_usd"] for r in rows]
    total = "?" if any(c is None for c in costs) else f"${sum(costs):.3f}"
    lines = [f"# Evals {when}", "",
             f"**{passed}/{len(rows)} passed** · model calls: {sum(r['calls'] for r in rows)} · cost: {total}", "",
             "| case | kind | result | why |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['kind']} | {'✅' if r['ok'] else '❌'} | {_cell(r['why'])} |" for r in rows]
    failed = [r for r in rows if not r["ok"]]
    if failed:
        lines += ["", "## Failed: the answers", ""]
        for r in failed:
            lines += [f"### {r['id']}", "", f"why: {r['why']}", "", "> " + r["answer"].replace("\n", "\n> "), ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    from dotenv import load_dotenv

    from app import tracing
    from app.agent.advisor import Advisor, load_agent_config
    from app.tracing import eval_config
    from app.agent.graph import build_agent
    from app.agent.models import QUESTION_KEY, ModelStalledError, Question, build_model
    from app.agent.rep_queue import InMemoryRepQueue
    from app.data.loader import load_all
    from app.profile import InMemoryProfiles
    from app.usage import turn_usage

    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BACKEND_DIR / ".env")
    tracing.configure(os.environ)  # LangSmith only with LANGSMITH_TRACING + LANGSMITH_API_KEY
    cfg = load_agent_config(BACKEND_DIR)
    sentence = cfg["texts"]["outOfScope"]
    data = load_all(BACKEND_DIR)
    profiles = InMemoryProfiles()  # main flow's profile cases: each one's profile, for a throwaway employee
    agent = build_agent(build_model(cfg["modelTimeoutSeconds"], thinking_level=cfg["geminiThinkingLevel"]),
                        data, InMemoryRepQueue(), cfg, profiles=profiles)  # car specs: the snapshot in git
    cars = [c["name"] for c in data.catalog.values()]
    engine = Advisor(data, InMemoryRepQueue(), cfg)  # the expected numbers: the same code, no model

    def expected_net(args: dict) -> Optional[float]:
        res = engine.calculate(args)
        return res["card"]["diff"]["net"] if res.get("status") == "ok" else None

    sets = {"off_topic": ("off topic", CASES_FILE, lambda m, s, case: judge(m, s)),
            "in_scope": ("in scope", IN_SCOPE_FILE, lambda m, s, case: judge_in_scope(m, s)),
            "recommend": ("recommend", RECOMMEND_FILE, lambda m, s, case: judge_expect(m, case["expect"], s, cars)),
            "recalc": ("recalc", RECALC_FILE, lambda m, s, case: judge_expect(m, case["expect"], s, cars)),
            "main_flow": ("main flow", MAIN_FLOW_FILE,
                          lambda m, s, case: judge_main(m, case, s, cars, expected_net))}
    names = [a for a in sys.argv[1:] if a in sets]
    only = [a for a in sys.argv[1:] if a not in sets]  # case ids: run just these, saves model quota
    prices = cfg["usage"]["prices"]
    rows = []
    for title, path, check in (sets[name] for name in names or list(sets)):
        cases = [c for c in json.loads(path.read_text(encoding="utf-8")) if not only or c["id"] in only]
        passed = 0
        print(f"\n== {title} ==")
        for case in cases:
            config = eval_config(f"eval-{uuid.uuid4()}", title, case["id"])  # LangSmith: tagged "eval"
            if "profile" in case:
                employee = f"eval-{uuid.uuid4().hex[:8]}"
                profiles.update(employee, case["profile"])
                config["configurable"]["employee_id"] = employee
            question_run = None
            try:
                for question in questions_of(case):
                    # the server's clock for each question, and every model's error (app/agent/models.py)
                    question_run = config["configurable"][QUESTION_KEY] = Question.start(cfg["questionTimeoutSeconds"])
                    out = agent.invoke({"messages": [("user", question)]}, config)
                # main flow judges the whole conversation itself; the others the last turn
                msgs = out["messages"] if path == MAIN_FLOW_FILE else last_turn(out["messages"])
                ok, why = check(msgs, sentence, case)
                answer = _final_text(out["messages"])
                usage = turn_usage(out["messages"], prices)
            except (Exception, ModelStalledError) as e:  # e.g. every model failed: counts as a fail, with the reason
                every = f" (every model: {question_run.summary()})" if question_run and question_run.errors else ""
                ok, why, answer = False, f"error: {type(e).__name__}: {e}{every}", ""
                usage = {"calls": 0, "cost_usd": None}
            passed += ok
            rows.append({"set": title, "kind": case.get("kind", title), "id": case["id"], "ok": ok, "why": why,
                         "answer": answer, "calls": usage["calls"], "cost_usd": usage["cost_usd"]})
            print(f'{"PASS" if ok else "FAIL"}  [{case.get("kind", title)}] {case["id"]}: {questions_of(case)[-1]}')
            if not ok:
                print(f"      why: {why}\n      answer: {answer[:300]}")
        print(f"{title}: {passed}/{len(cases)} passed")
    now = datetime.now()
    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = RESULTS_DIR / f"{'+'.join(names or list(sets))}-{now:%Y-%m-%d-%H%M}.md"
    out_file.write_text(results_markdown(rows, f"{now:%Y-%m-%d %H:%M}"), encoding="utf-8")
    print(f"\nresults: {out_file.relative_to(BACKEND_DIR)}")


if __name__ == "__main__":
    main()
