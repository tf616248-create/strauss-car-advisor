"""The recommendation evals (evals/recommend.json): the cases, and the judge that reads each case's
"expect". The real model runs them in evals/run_off_topic.py (needs keys) - not here."""
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from evals.run_off_topic import RECOMMEND_FILE, judge_expect

SENTENCE = "המשפט הקבוע"
CARS = ["BYD DOLPHIN", "KONA EV"]


def turn(final, calls=()):
    msgs = [HumanMessage(content="שאלה")]
    for i, (name, args) in enumerate(calls):
        msgs.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(i)}]))
        msgs.append(ToolMessage(content="{}", tool_call_id=str(i), name=name))
    msgs.append(AIMessage(content=final))
    return msgs


def test_five_cases_with_expectations():
    cases = json.loads(RECOMMEND_FILE.read_text(encoding="utf-8"))
    assert [c["id"] for c in cases] == ["comfort-vague", "family-safe", "most-beautiful", "dolphin-consumption",
                                        "recommend-no-details"]
    assert all(c["expect"] for c in cases)


def test_no_tools_and_no_car_names():
    expect = {"no_tools": ["rank_options"], "no_car_names": True, "text_any": [["מבחינת"]]}
    assert judge_expect(turn("נוח מבחינת מה?"), expect, SENTENCE, CARS) == (True, "")
    ok, why = judge_expect(turn("יש את BYD DOLPHIN"), expect, SENTENCE, CARS)
    assert not ok and "BYD DOLPHIN" in why
    ok, why = judge_expect(turn("נוח מבחינת מה?", [("rank_options", {})]), expect, SENTENCE, CARS)
    assert not ok and "rank_options" in why


def test_tool_and_its_arguments():
    expect = {"tools": ["rank_options"], "tool_args": {"rank_options": {"sort_by": "safety"}},
              "tool_args_any": {"rank_options": ["min_seats", "body_type"]}}
    good = turn("סידרתי", [("rank_options", {"sort_by": "safety", "body_type": ["פנאי-שטח"]})])
    assert judge_expect(good, expect, SENTENCE, CARS) == (True, "")
    assert not judge_expect(turn("x", [("rank_options", {"sort_by": "net", "min_seats": 5})]), expect, SENTENCE, CARS)[0]
    assert not judge_expect(turn("x", [("rank_options", {"sort_by": "safety"})]), expect, SENTENCE, CARS)[0]
    assert not judge_expect(turn("x"), expect, SENTENCE, CARS)[0]


def test_text_groups_and_refusal():
    expect = {"text_any": [["159"], ["ראשוני"]], "not_refused": True}
    assert judge_expect(turn("159 Wh, נתון ראשוני"), expect, SENTENCE, CARS)[0]
    assert not judge_expect(turn("159 Wh"), expect, SENTENCE, CARS)[0]
    assert not judge_expect(turn("159 ראשוני " + SENTENCE), expect, SENTENCE, CARS)[0]
