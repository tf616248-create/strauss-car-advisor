"""The profile through the agent and the API, with a scripted fake model (no API calls): the
the profile in every conversation, "עדכנתי בפרופיל", the payslip, the
endpoints, and what reaches LangSmith (field names, never values)."""
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app import profile as profile_mod
from app.agent.advisor import load_agent_config
from app.agent.graph import TOOL_NAMES, build_agent
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.payslip import InMemoryPayslips, PayslipReader
from app.profile import InMemoryProfiles
from tests import payslip_fixture as dummy
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.agent.test_agent_graph import ScriptedModel, call
from tests.api.test_api import chat, events
from tests.test_payslip import reader_model
from tests.test_profile import FULL


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


class RecordingModel(ScriptedModel):
    """The scripted model, keeping what it was given (the system prompt included)."""
    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).seen.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


def results(msgs, name):
    return [json.loads(m.content) for m in msgs if isinstance(m, ToolMessage) and m.name == name]


def agent_with(data, cfg, script, profiles):
    RecordingModel.seen = []
    return build_agent(RecordingModel(messages=iter(script)), data, InMemoryRepQueue(), cfg, profiles=profiles)


def ask(agent, text, employee="E01", thread="t"):
    return agent.invoke({"messages": [("user", text)]},
                        {"configurable": {"thread_id": thread, "employee_id": employee}})["messages"]


# --- the tool --------------------------------------------------------------------------------

# --- the profile in the conversation ----------------------------------------------------------

def test_every_conversation_gets_the_profile_filled_in_by_the_code(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E01", FULL)
    alt = {"alternative_kind": "car", "alternative_car": "EV3"}
    agent = agent_with(data, cfg, [call("calculate", alt), AIMessage(content="הנטו"),
                                   call("calculate", alt, 1), AIMessage(content="הנטו")], profiles)
    for thread in ("first", "second"):  # a new conversation as well
        res = results(ask(agent, "מה אם אעבור ל-EV3?", thread=thread), "calculate")[-1]
        assert res["status"] == "ok"
        assert res["card"]["your_data"]["base"]["source"] == cfg["texts"]["sources"]["profile"]


def test_another_employees_profile_is_not_used(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E02", FULL)
    agent = agent_with(data, cfg, [call("calculate", {"alternative_kind": "car", "alternative_car": "EV3"}),
                                   AIMessage(content="חסר")], profiles)
    assert results(ask(agent, "EV3?", employee="E01"), "calculate")[0]["status"] == "missing"


def test_a_value_written_in_the_chat_updates_the_profile_and_kobi_says_so(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E01", FULL)
    agent = agent_with(data, cfg, [call("calculate", {"base": 15000, "alternative_kind": "waiver"}),
                                   AIMessage(content="עדכנתי בפרופיל")], profiles)
    res = results(ask(agent, "השכר שלי עכשיו 15,000"), "calculate")[0]
    assert profiles.get("E01")["base"] == 15000
    assert res["profile_updated"] == ["base"]
    assert "עדכנתי בפרופיל" in res["message_profile"]


def test_the_prompt_lists_the_profile_fields_by_name_never_their_values(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E01", {"occupation": "מנהל/ת אזור מכירות", "base": 14321})
    agent = agent_with(data, cfg, [AIMessage(content="שלום")], profiles)
    ask(agent, "שלום")
    system = RecordingModel.seen[0][0]
    assert isinstance(system, SystemMessage)
    labels = cfg["texts"]["profile"]["labels"]
    assert labels["base"] in system.content and labels["credit_points"] in system.content
    assert "14321" not in system.content and "14,321" not in system.content
    assert "מנהל/ת אזור מכירות" in system.content  # the occupation list of the base prompt, as always
    assert cfg["profile"]["link"] in system.content


def test_without_an_employee_the_prompt_has_no_profile_section(data, cfg):
    agent = agent_with(data, cfg, [AIMessage(content="שלום")], InMemoryProfiles())
    agent.invoke({"messages": [("user", "שלום")]}, {"configurable": {"thread_id": "t"}})
    assert cfg["texts"]["profile"]["promptHeading"] not in RecordingModel.seen[0][0].content


# --- the API ----------------------------------------------------------------------------------

def make(data, cfg, script=(), image_model=None, profiles=None):
    profiles = profiles if profiles is not None else InMemoryProfiles()
    auth = make_auth()
    app = create_app(data=data, model=ScriptedModel(messages=iter(list(script))), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode="x", employee_auth=auth,
                     payslips=InMemoryPayslips(), payslip_reader=PayslipReader(image_model, None, cfg),
                     profiles=profiles)
    return authed(app, auth), profiles, app


def test_the_profile_endpoints_need_a_login(data, cfg):
    _, _, app = make(data, cfg)
    client = TestClient(app)
    assert client.get("/profile").status_code == 401
    assert client.patch("/profile", json={"fields": {"base": 1}}).status_code == 401


def test_read_an_empty_profile(data, cfg):
    client, _, _ = make(data, cfg)
    assert client.get("/profile").json() == {"employee_id": "E01", "fields": {}, "sources": {}, "group": None,
                                             "address": "plural"}


def test_update_then_read_with_the_group_computed(data, cfg):
    client, profiles, _ = make(data, cfg)
    r = client.patch("/profile", json={"fields": {"occupation": "מפתחת תוכנה", "base": 15000, "children": 2}})
    assert r.status_code == 200
    body = r.json()
    assert body["fields"] == {"occupation": "מפתח/ת תוכנה", "base": 15000, "children": 2}
    assert body["group"] == "ב"  # read only: computed from the occupation, not kept
    assert body["sources"] == {"occupation": "profile", "base": "profile", "children": "profile"}
    assert "group" not in profiles.get("E01")
    assert client.get("/profile").json() == body


def test_a_bad_value_is_refused_and_nothing_is_kept(data, cfg):
    client, profiles, _ = make(data, cfg)
    r = client.patch("/profile", json={"fields": {"base": 15000, "pension_pct": 40, "occupation": "שף"}})
    assert r.status_code == 422
    invalid = r.json()["detail"]["invalid"]
    assert set(invalid) == {"pension_pct", "occupation"}
    assert invalid["pension_pct"]["range"] == cfg["ranges"]["pension_pct"]
    assert 2 <= len(invalid["occupation"]["suggestions"]) <= 3
    assert profiles.get("E01") == {}


def test_the_group_cannot_be_written(data, cfg):
    client, _, _ = make(data, cfg)
    r = client.patch("/profile", json={"fields": {"group": "ד"}})
    assert r.status_code == 422 and "group" in r.json()["detail"]["invalid"]


def test_a_payslip_updates_the_profile_and_kobi_is_told(data, cfg):
    client, profiles, app = make(data, cfg, script=[AIMessage(content="שלום"), AIMessage(content="לקחתי")],
                                 image_model=reader_model())
    tid = chat(client, "שלום")[0][1]["thread_id"]
    events(client.post(f"/chat/{tid}/payslip", content=dummy.png(), headers={"Content-Type": "image/png"}))
    assert {k: profiles.get("E01")[k] for k in dummy.FOUND} == dummy.FOUND
    assert client.get("/profile").json()["sources"] == {k: "payslip" for k in dummy.FOUND}
    from app.api.common import messages_of
    note = [m for m in messages_of(app.state.agent, tid) if m.type == "human"][-1]
    assert cfg["texts"]["profile"]["noteUpdated"] in note.content


def test_the_chat_passes_the_employee_to_the_tools(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E01", FULL)
    client, _, _ = make(data, cfg, script=[call("calculate", {"alternative_kind": "car", "alternative_car": "EV3"}),
                                           AIMessage(content="הנטו")], profiles=profiles)
    card = next(d for k, d in chat(client, "EV3?") if k == "card")
    assert card["card"]["your_data"]["base"]["source"] == cfg["texts"]["sources"]["profile"]


def test_a_value_from_the_chat_shows_as_from_the_chat(data, cfg):
    profiles = InMemoryProfiles()
    profiles.update("E01", FULL)
    client, _, _ = make(data, cfg, script=[call("calculate", {"base": 15000, "alternative_kind": "waiver"}),
                                           AIMessage(content="עדכנתי בפרופיל")], profiles=profiles)
    chat(client, "השכר שלי 15,000")
    sources = client.get("/profile").json()["sources"]
    assert sources["base"] == "chat" and sources["bonus"] == "profile"


# --- LangSmith: the field names only ----------------------------------------------------------

def test_profile_traces_carry_field_names_only(data, cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(profile_mod, "trace_profile", lambda event, fields: sent.append((event, list(fields))))
    client, _, _ = make(data, cfg)
    client.patch("/profile", json={"fields": {"base": 15432, "occupation": "מפתח/ת תוכנה"}})
    client.get("/profile")
    assert ("profile_updated", ["base", "occupation"]) in sent
    assert ("profile_read", ["base", "occupation"]) in sent
    assert "15432" not in json.dumps(sent, ensure_ascii=False)


def test_the_trace_function_returns_names_only():
    assert profile_mod.trace_profile("profile_updated", ["base"]) == {"event": "profile_updated", "fields": ["base"]}
