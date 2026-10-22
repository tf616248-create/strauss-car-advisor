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


def test_six_cases_with_expectations():
    cases = json.loads(RECOMMEND_FILE.read_text(encoding="utf-8"))
    assert [c["id"] for c in cases] == ["comfort-vague", "family-safe", "roomy-safe", "most-beautiful",
                                        "dolphin-consumption", "recommend-no-details"]
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


def test_recalc_cases_have_two_turns():
    """The PDF check: the employee corrects a detail or switches car, and calculate runs again."""
    from evals.run_off_topic import RECALC_FILE
    cases = json.loads(RECALC_FILE.read_text(encoding="utf-8"))
    assert [c["id"] for c in cases] == ["correct-salary", "switch-car"]
    assert all(len(c["turns"]) == 2 and c["expect"]["tools"] == ["calculate"] for c in cases)


def test_questions_of_and_last_turn():
    from evals.run_off_topic import last_turn, questions_of
    assert questions_of({"question": "א"}) == ["א"]
    assert questions_of({"turns": ["א", "ב"]}) == ["א", "ב"]
    first = turn("נטו 1", [("calculate", {"base": 18500})])
    second = turn("נטו 2", [("calculate", {"base": 19500})])
    expect = {"tools": ["calculate"], "tool_args": {"calculate": {"base": 18500}}}
    assert judge_expect(first + second, expect, SENTENCE, CARS)[0]  # the whole thread would pass...
    assert not judge_expect(last_turn(first + second), expect, SENTENCE, CARS)[0]  # ...the last turn alone does not
