"""The employee's name and form of address (פנייה: male / female / plural, plural until chosen).

The name never reaches the model or LangSmith: the prompt has the placeholder {name}, and the server
puts the first name in its place as the answer streams to the employee (app/names.py). Only the form of
address is in the prompt. The fixed texts that speak to the employee are worded neutrally."""
import json
import re

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.employees import InMemoryEmployees
from app.names import NameFiller, fill, first_name
from app.profile import InMemoryProfiles, validate_settings
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.test_api import events
from tests.test_profile_agent import RecordingModel


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


# --- the config -------------------------------------------------------------------------------

def test_three_forms_of_address_plural_until_chosen(cfg):
    a = cfg["address"]
    assert a["options"] == ["male", "female", "plural"]
    assert set(a["labels"]) == set(a["options"])
    assert cfg["settings"]["defaults"]["address"] == "plural"
    assert a["placeholder"] == "{name}"


# the forms that speak to one gender or to many: none in a fixed text (agent.json texts)
NOT_NEUTRAL = re.compile(r"(שלכם|לכם|אתכם|נסו |רוצים|תרצו|תוכלו|תחליפו|תעברו|תוותרו|כתבו|שלך|\bלך\b|אתה|תוכל |רוצה|תעלו|תכתבו)")


def strings(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from strings(v, f"{path}.{k}")
    elif isinstance(o, str):
        yield path, o


def test_the_fixed_texts_to_the_employee_are_neutral(cfg):
    """Refusals, the usage limit, the payslip's messages, eligibility reasons...: one wording fits all three.
    (A text that could not be neutral would get a version per form of address - none needed so far.)"""
    found = [(p, s) for p, s in strings(cfg["texts"], "texts")
             if NOT_NEUTRAL.search(s) and not p.endswith("extractPrompt")]
    assert found == []


def test_the_out_of_scope_sentence_is_still_one_fixed_sentence(cfg):
    assert cfg["texts"]["outOfScope"].startswith("אני כובי")


# --- the name: first name only, put in by the server ------------------------------------------

@pytest.mark.parametrize("full, first", [("נועה לוי", "נועה"), ("  דן  מזרחי ", "דן"), ("", None), (None, None)])
def test_first_name(full, first):
    assert first_name(full) == first


def test_fill():
    assert fill("שלום {name}, הנטו עולה", "נועה") == "שלום נועה, הנטו עולה"
    assert fill("בלי שם", "נועה") == "בלי שם"
    assert fill("שלום {name}, הנה", None) == "שלום, הנה"  # no name: the sentence still reads right


def test_the_name_is_filled_in_while_streaming_even_when_split_between_chunks():
    f = NameFiller("נועה")
    out = "".join(f.feed(t) for t in ["שלום {", "na", "me}", ", הנטו {", "x} עולה"]) + f.flush()
    assert out == "שלום נועה, הנטו {x} עולה"
    g = NameFiller("נועה")
    assert g.feed("סוף {na") == "סוף"  # the space waits with it: without a name it would go too
    assert g.flush() == " {na"  # an unfinished placeholder at the end is written as it is


# --- the form of address is kept with the settings --------------------------------------------

def test_validate_the_form_of_address(cfg):
    assert validate_settings({"address": "female"}, cfg) == ({"address": "female"}, {})
    assert validate_settings({"address": "x"}, cfg)[1] == {"address": {"options": ["male", "female", "plural"]}}


def make(data, cfg, script=(), names=None):
    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    auth = make_auth()
    RecordingModel.seen = []
    app = create_app(data=data, model=RecordingModel(messages=iter(list(script))), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode="x", employee_auth=auth, profiles=profiles,
                     employees=InMemoryEmployees(names if names is not None else {"E01": "נועה לוי"}))
    return authed(app, auth), profiles, app


def test_the_profile_has_the_form_of_address_plural_by_default(data, cfg):
    client, _, _ = make(data, cfg)
    assert client.get("/profile").json()["address"] == "plural"


def test_change_it_in_the_profile(data, cfg):
    client, profiles, _ = make(data, cfg)
    r = client.patch("/profile", json={"fields": {"base": 15000}, "address": "female"})
    assert r.status_code == 200 and r.json()["address"] == "female"
    assert profiles.settings("E01")["address"] == "female"
    assert client.patch("/profile", json={"address": "male"}).json()["address"] == "male"  # alone, too


def test_a_bad_form_of_address_keeps_nothing(data, cfg):
    client, profiles, _ = make(data, cfg)
    r = client.patch("/profile", json={"fields": {"base": 15000}, "address": "formal"})
    assert r.status_code == 422 and set(r.json()["detail"]["invalid"]) == {"address"}
    assert profiles.get("E01") == {} and profiles.settings("E01")["address"] == "plural"


# --- the prompt: the form of address, the name as a placeholder only --------------------------

def system_prompt(client, address=None):
    if address:
        client.patch("/profile", json={"address": address})
    events(client.post("/chat", json={"message": "שלום"}))
    return RecordingModel.seen[-1][0].content


@pytest.mark.parametrize("address", ["male", "female", "plural"])
def test_the_prompt_says_how_to_address_the_employee(data, cfg, address):
    client, _, _ = make(data, cfg, [AIMessage(content="היי")])
    prompt = system_prompt(client, address)
    assert f'פנה בלשון {cfg["address"]["labels"][address]}' in prompt
    for other in set(cfg["address"]["options"]) - {address}:
        assert f'פנה בלשון {cfg["address"]["labels"][other]}' not in prompt


def test_plural_until_the_employee_chooses(data, cfg):
    client, _, _ = make(data, cfg, [AIMessage(content="היי")])
    assert f'פנה בלשון {cfg["address"]["labels"]["plural"]}' in system_prompt(client)


def test_with_a_name_the_prompt_has_the_placeholder_and_the_rule_never_the_name(data, cfg):
    client, _, _ = make(data, cfg, [AIMessage(content="היי")])
    prompt = system_prompt(client)
    assert "אתה מדבר עם {name}" in prompt
    assert "בפתיחה" in prompt and "לא בכל הודעה" in prompt
    # LangSmith gets the prompt: the name is not in it ("לוי" alone would match "בגלוי", already in the prompt)
    assert "נועה" not in prompt and "נועה לוי" not in prompt


def test_without_a_name_no_placeholder(data, cfg):
    client, _, _ = make(data, cfg, [AIMessage(content="היי")], names={})
    prompt = system_prompt(client)
    assert "{name}" not in prompt
    assert f'פנה בלשון {cfg["address"]["labels"]["plural"]}' in prompt


# --- the answer: the server puts the name in ---------------------------------------------------

def test_the_employee_sees_the_name_the_model_and_langsmith_do_not(data, cfg):
    client, _, _ = make(data, cfg, [AIMessage(content="שלום {name}, אני כובי. מה תרצו לבדוק?")])
    evs = events(client.post("/chat", json={"message": "שלום"}))
    shown = "".join(d["text"] for k, d in evs if k == "token")
    assert shown == "שלום נועה, אני כובי. מה תרצו לבדוק?"
    tid = evs[0][1]["thread_id"]
    restored = client.get(f"/chat/{tid}").json()["messages"]
    assert restored[-1] == {"role": "assistant", "text": shown}  # after a reload, too
    assert all("נועה" not in json.dumps([m.content for m in seen], ensure_ascii=False)
               for seen in RecordingModel.seen)  # every model input: no name


def test_the_trace_metadata_has_the_form_of_address_not_the_name(data, cfg):
    from app.api.common import thread_config
    config = thread_config("t", "E01", address="female")
    assert config["metadata"]["address"] == "female"
    assert "נועה" not in json.dumps(config, ensure_ascii=False)


def test_no_name_no_placeholder_left_on_screen(data, cfg):
    client, _, _ = make(data, cfg, [AIMessage(content="שלום {name}, אני כובי.")], names={})
    evs = events(client.post("/chat", json={"message": "שלום"}))
    assert "".join(d["text"] for k, d in evs if k == "token") == "שלום, אני כובי."


def test_profile_and_settings_need_a_login_still(data, cfg):
    _, _, app = make(data, cfg)
    assert TestClient(app).patch("/profile", json={"address": "male"}).status_code == 401
