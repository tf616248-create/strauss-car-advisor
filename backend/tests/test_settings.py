"""The employee's settings ("התאמה אישית"): light or dark, and Kobi's tone. Kept on the server with the
profile (table employee_profile). The tone changes the style only: a fake-model run in the "funny" tone
gives the same tool results, and the prompt keeps every rule of the professional one."""
import json
import os
import uuid

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.advisor import load_agent_config
from app.agent.prompt import build_prompt
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.profile import InMemoryProfiles, validate_settings
from evals.run_off_topic import judge_main
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.test_agent_graph import call
from tests.test_profile import FULL
from tests.test_profile_agent import RecordingModel, agent_with, ask

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


# --- the config ------------------------------------------------------------------------------

def test_three_tones_in_agent_json_professional_by_default(cfg):
    tones = cfg["tones"]
    assert tones["default"] == "professional"
    assert list(tones["styles"]) == ["professional", "friendly", "funny"]
    assert tones["styles"]["professional"] is None  # the professional tone is the prompt's "## טון", as it was
    for name in ("friendly", "funny"):
        assert tones["styles"][name].strip()
    assert "בלי הומור על שכר, מס או סירוב" in tones["rule"]
    assert cfg["settings"] == {"themes": ["light", "dark"], "defaults": {"theme": "light", "tone": "professional"}}


def test_validate_settings(cfg):
    assert validate_settings({"theme": "dark", "tone": "funny"}, cfg) == ({"theme": "dark", "tone": "funny"}, {})
    clean, bad = validate_settings({"theme": "pink", "tone": "rude", "font": "x"}, cfg)
    assert clean == {}
    assert bad == {"theme": {"options": ["light", "dark"]}, "tone": {"options": ["professional", "friendly", "funny"]},
                   "font": {"reason": "unknown_field"}}


# --- the stores -------------------------------------------------------------------------------

@pytest.fixture(params=["memory", "postgres"])
def store(request, cfg):
    emp = f"test-{uuid.uuid4().hex[:8]}"
    if request.param == "memory":
        yield InMemoryProfiles(cfg["settings"]["defaults"]), emp
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresEmployees, PostgresProfiles, make_pool

    pool = make_pool(DATABASE_URL)
    employees = PostgresEmployees(pool, {emp: "עובד דמה"})
    employees.setup()
    profiles = PostgresProfiles(pool, cfg["settings"]["defaults"])
    profiles.setup()
    yield profiles, emp
    employees.delete([emp])
    pool.close()


def test_the_defaults_light_and_professional_even_without_a_profile(store):
    profiles, emp = store
    assert profiles.settings(emp) == {"theme": "light", "tone": "professional"}


def test_settings_are_kept_and_leave_the_profile_alone(store):
    profiles, emp = store
    profiles.update(emp, {"base": 15000})
    profiles.update_settings(emp, {"theme": "dark"})
    profiles.update_settings(emp, {"tone": "funny"})
    assert profiles.settings(emp) == {"theme": "dark", "tone": "funny"}
    assert profiles.get(emp) == {"base": 15000}
    assert profiles.sources(emp) == {"base": "profile"}


# --- the API ----------------------------------------------------------------------------------

def make(data, cfg):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    auth = make_auth()
    app = create_app(data=data, model=RecordingModel(messages=iter([])), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode="x", employee_auth=auth, profiles=profiles)
    return authed(app, auth), profiles, app


def test_the_settings_endpoints_need_a_login(data, cfg):
    _, _, app = make(data, cfg)
    assert TestClient(app).get("/settings").status_code == 401
    assert TestClient(app).patch("/settings", json={"theme": "dark"}).status_code == 401


def test_read_and_change_the_settings(data, cfg):
    client, profiles, _ = make(data, cfg)
    assert client.get("/settings").json() == {"theme": "light", "tone": "professional"}
    r = client.patch("/settings", json={"tone": "friendly"})
    assert r.status_code == 200 and r.json() == {"theme": "light", "tone": "friendly"}
    assert profiles.settings("E01")["tone"] == "friendly"


def test_a_bad_setting_is_refused_and_nothing_is_kept(data, cfg):
    client, profiles, _ = make(data, cfg)
    r = client.patch("/settings", json={"theme": "dark", "tone": "sarcastic"})
    assert r.status_code == 422 and set(r.json()["detail"]["invalid"]) == {"tone"}
    assert profiles.settings("E01") == {"theme": "light", "tone": "professional"}


# --- the tone in the prompt -------------------------------------------------------------------

def system_prompt(data, cfg, tone):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    profiles.update_settings("E01", {"tone": tone})
    agent = agent_with(data, cfg, [AIMessage(content="שלום")], profiles)
    ask(agent, "שלום")
    return RecordingModel.seen[0][0].content


def test_the_hard_rule_is_in_every_prompt(data, cfg):
    assert cfg["tones"]["rule"] in build_prompt(data, cfg)
    for tone in cfg["tones"]["styles"]:
        assert cfg["tones"]["rule"] in system_prompt(data, cfg, tone)


def test_professional_is_the_prompt_as_it_was(data, cfg):
    prompt = system_prompt(data, cfg, "professional")
    assert prompt.startswith(build_prompt(data, cfg))
    assert cfg["tones"]["heading"] not in prompt
    for tone in ("friendly", "funny"):
        assert cfg["tones"]["styles"][tone] not in prompt


@pytest.mark.parametrize("tone", ["friendly", "funny"])
def test_another_tone_adds_its_style_and_keeps_every_rule(data, cfg, tone):
    """The whole professional prompt is still there, word for word (rules, refusals, the rep, 'סידרתי לפי
    הנתונים', the fixed out-of-scope sentence); the tone's style block comes after it."""
    base = build_prompt(data, cfg)
    prompt = system_prompt(data, cfg, tone)
    assert prompt.startswith(base)
    added = prompt[len(base):]
    assert cfg["tones"]["styles"][tone] in added
    for kept in (cfg["texts"]["outOfScope"], cfg["texts"]["repSent"], "סידרתי לפי הנתונים", "## חוקים שאסור לעבור עליהם"):
        assert kept in prompt


def test_the_tone_applies_from_the_next_message_without_a_new_conversation(data, cfg):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    agent = agent_with(data, cfg, [AIMessage(content="א"), AIMessage(content="ב")], profiles)
    ask(agent, "שלום", thread="same")
    profiles.update_settings("E01", {"tone": "funny"})
    ask(agent, "ועוד", thread="same")
    first, second = RecordingModel.seen[0][0].content, RecordingModel.seen[1][0].content
    assert cfg["tones"]["styles"]["funny"] not in first
    assert cfg["tones"]["styles"]["funny"] in second


# --- the "funny" scenario: the numbers and the rules do not move --------------------------------

def run(data, cfg, tone, final):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    profiles.update("E01", FULL)
    profiles.update_settings("E01", {"tone": tone})
    agent = agent_with(data, cfg, [call("calculate", {"alternative_kind": "car", "alternative_car": "EV3"}),
                                   AIMessage(content=final)], profiles)
    return ask(agent, "מה יקרה לנטו שלי אם אעבור ל-EV3?")


def results(msgs, name):
    return [json.loads(m.content) for m in msgs if isinstance(m, ToolMessage) and m.name == name]


def test_funny_gives_the_same_numbers_and_passes_the_same_checks(data, cfg):
    professional = run(data, cfg, "professional", "תשובה")
    net = results(professional, "calculate")[0]["card"]["diff"]["net"]
    joke = f"EV3 שקט כמו ספרייה, אבל הנטו מדבר ברור: הוא {'עולה' if net > 0 else 'יורד'} ב-{abs(net):,} ₪ בחודש."
    funny = run(data, cfg, "funny", joke)
    # the tools do not know the tone: the same card, the same numbers
    assert results(funny, "calculate") == results(professional, "calculate")
    expected = {**FULL, "group": "ג", "alternative_kind": "car", "alternative_car": "EV3"}
    case = {"expect": {"net_from_calculate": expected, "numbers_from_tools": True, "not_refused": True}}
    ok, why = judge_main(funny, case, cfg["texts"]["outOfScope"], ["EV3"], lambda a: net)
    assert ok, why


def test_funny_with_a_changed_number_fails_the_check(data, cfg):
    professional = run(data, cfg, "professional", "תשובה")
    net = results(professional, "calculate")[0]["card"]["diff"]["net"]
    funny = run(data, cfg, "funny", f"בערך {abs(net) + 1000:,} ₪, תן או קח. 😄")
    case = {"expect": {"net_from_calculate": {**FULL, "alternative_kind": "car", "alternative_car": "EV3"},
                       "numbers_from_tools": True}}
    ok, _ = judge_main(funny, case, cfg["texts"]["outOfScope"], ["EV3"], lambda a: net)
    assert not ok
