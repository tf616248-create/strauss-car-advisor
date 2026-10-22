"""The group comes only from the code and the profile - no occupation_to_group tool.

The prompt's profile has the group, whether the car is mandatory, whether a waiver is allowed and the
maintenance, all computed from the occupation ("לפי העיסוק"), or "חסר" without one. An occupation written in
the chat is recognized (and kept) or not_found with close ones. calculate has no group parameter: only
employee_stated_group, when the employee claims another group - the contradiction and the rep as before."""
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.advisor import load_agent_config
from app.agent.graph import TOOL_NAMES, make_tools
from app.agent.rep_queue import InMemoryRepQueue
from app.profile import InMemoryProfiles
from tests.conftest import BACKEND_DIR
from tests.test_agent_graph import call
from tests.test_profile import FULL
from tests.test_profile_agent import RecordingModel, agent_with, ask


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def results(msgs, name):
    return [json.loads(m.content) for m in msgs if isinstance(m, ToolMessage) and m.name == name]


def tool_calls(msgs):
    return [tc["name"] for m in msgs if isinstance(m, AIMessage) for tc in m.tool_calls]


# --- no tool, no group parameter ----------------------------------------------------------------

def test_no_occupation_to_group_tool(data, cfg):
    assert "occupation_to_group" not in TOOL_NAMES
    assert "occupation_to_group" not in {t.name for t in make_tools(data, InMemoryRepQueue(), cfg)}
    assert "occupation_to_group" not in cfg["texts"]["steps"]


@pytest.mark.parametrize("tool", ["calculate", "check_eligibility", "rank_options"])
def test_the_tools_take_no_group_only_what_the_employee_stated(data, cfg, tool):
    t = next(t for t in make_tools(data, InMemoryRepQueue(), cfg) if t.name == tool)
    params = t.args
    assert "group" not in params
    assert "employee_stated_group" in params


# --- the profile in the prompt: the group from the occupation ---------------------------------

def system_prompt(data, cfg, fields):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    profiles.update("E01", fields)
    agent = agent_with(data, cfg, [AIMessage(content="קבוצה ב")], profiles)
    msgs = ask(agent, "באיזו קבוצה אני?")
    return RecordingModel.seen[0][0].content, msgs


def test_which_group_am_i_is_answered_from_the_profile_without_a_tool(data, cfg):
    prompt, msgs = system_prompt(data, cfg, {"occupation": "מפתח/ת תוכנה"})
    occ = data.occupations["מפתח/ת תוכנה"]
    t = cfg["texts"]["profile"]
    assert f'{t["derived"]["group"]}: {occ["group"]} ({t["byOccupation"]})' in prompt
    assert f'{t["derived"]["carMandatory"]}: {t["no"]} ({t["byOccupation"]})' in prompt
    assert f'{t["derived"]["waiverAllowed"]}: {t["yes"]} ({t["byOccupation"]})' in prompt
    assert f'{t["derived"]["maintenance"]}: {occ["maintenance"]:,} ₪ ({t["byOccupation"]})' in prompt
    assert "את הקבוצה לוקחים מהפרופיל, לא שואלים עליה ולא מחשבים אותה" in prompt
    assert tool_calls(msgs) == []  # answered from the prompt's profile, no tool


def test_without_an_occupation_the_group_is_missing(data, cfg):
    prompt, _ = system_prompt(data, cfg, {"base": 15000})
    t = cfg["texts"]["profile"]
    assert f'{t["derived"]["group"]}: {t["missingValue"]}' in prompt


def test_langsmith_gets_no_profile_values_only_names_the_occupation_and_salary_stay_out(data, cfg):
    """The prompt (which LangSmith gets) has the field names, and what the code derives from the occupation;
    never the occupation itself or the salary values."""
    prompt, _ = system_prompt(data, cfg, {**FULL, "base": 14321})
    assert "14321" not in prompt and "14,321" not in prompt
    profile_part = prompt.split("## " + cfg["texts"]["profile"]["promptHeading"], 1)[1]
    assert "מנהל/ת אזור מכירות" not in profile_part


# --- an occupation written in the chat: recognized, or not_found with close ones --------------

def run(data, cfg, script, fields=None):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    if fields:
        profiles.update("E01", fields)
    queue = InMemoryRepQueue()
    from app.agent.graph import build_agent
    RecordingModel.seen = []
    agent = build_agent(RecordingModel(messages=iter(script)), data, queue, cfg, profiles=profiles)
    return agent, profiles, queue


def test_a_recognized_occupation_is_kept_in_the_profile(data, cfg):
    agent, profiles, _ = run(data, cfg, [call("calculate", {"occupation": "מפתחת תוכנה"}), AIMessage(content="שמרתי")])
    res = results(ask(agent, "אני מפתחת תוכנה"), "calculate")[0]
    assert res["occupation"] == {"status": "recognized", "occupation": "מפתח/ת תוכנה"}
    assert profiles.get("E01")["occupation"] == "מפתח/ת תוכנה"
    assert "עדכנתי בפרופיל" in res["message_profile"]


def test_an_unknown_occupation_gives_close_ones_and_kobi_asks(data, cfg):
    agent, profiles, _ = run(data, cfg, [call("calculate", {"occupation": "שף"}), AIMessage(content="מה העיסוק שלך?")])
    msgs = ask(agent, "אני שף")
    res = results(msgs, "calculate")[0]
    assert res["occupation"]["status"] == "not_found"
    assert 2 <= len(res["occupation"]["suggestions"]) <= 3
    assert "אל תנחש" in res["instruction"]
    assert "occupation" not in profiles.get("E01")  # nothing guessed, nothing kept
    assert msgs[-1].content == "מה העיסוק שלך?"


# --- the employee claims another group: the contradiction, then the rep -----------------------

def test_a_stated_group_is_a_contradiction_then_the_rep_and_the_rep_answer_wins(data, cfg):
    alt = {"alternative_kind": "car", "alternative_car": "EV3"}
    script = [call("calculate", {**alt, "employee_stated_group": "ד"}), AIMessage(content="לפי העיסוק ג"),
              call("ask_rep", {"fields": ["group"], "question": "העובד מתעקש שהוא בקבוצה ד"}),
              AIMessage(content="שלחתי לנציג"),
              call("calculate", {**alt, "employee_stated_group": "ד"}, 2), AIMessage(content="עודכן")]
    agent, _, queue = run(data, cfg, script, fields=FULL)  # FULL: מנהל/ת אזור מכירות, group ג
    first = results(ask(agent, "אני בקבוצה ד"), "calculate")[0]
    assert first["status"] == "contradiction"
    assert first["employee_group"] == "ד" and first["occupation_group"] == "ג"
    assert results(ask(agent, "אני מתעקש"), "ask_rep")[0]["status"] == "sent"
    queue.answer(queue.pending("t")[0]["id"], {"group": "ד"})
    last = results(ask(agent, "הנציג ענה?"), "calculate")[-1]
    assert last["status"] in ("ok", "not_eligible")  # the rep's answer wins: no more contradiction
    if last["status"] == "ok":
        assert last["card"]["your_data"]["group"] == {"value": "ד", "source": cfg["texts"]["sources"]["rep"]}
