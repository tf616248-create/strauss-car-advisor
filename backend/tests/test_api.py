"""FastAPI server: SSE chat, conversation restore, rep screen API. Scripted fake model."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.main import InMemoryNotifier, create_app
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args
from tests.test_agent_graph import ScriptedModel, call
from tests.test_agent_models import Overloaded

PASS = "test-pass"


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def make(data, cfg, script=None, model=None, passcode=PASS):
    queue, notifier = InMemoryRepQueue(), InMemoryNotifier()
    model = model or ScriptedModel(messages=iter(script))
    app = create_app(data=data, model=model, rep_queue=queue, notifier=notifier, cfg=cfg, rep_passcode=passcode)
    return TestClient(app), queue, notifier


def events(response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def chat(client, message, thread_id=None):
    body = {"message": message}
    if thread_id:
        body["thread_id"] = thread_id
    r = client.post("/chat", json=body)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    return events(r)


def kinds(evs):
    return [k for k, _ in evs]


# --- health -----------------------------------------------------------------------


def test_health(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.get("/health").json()["status"] == "ok"


# --- chat over SSE ----------------------------------------------------------------


def test_new_conversation_gets_an_id_and_streams_text(data, cfg):
    client, _, _ = make(data, cfg, script=[AIMessage(content="שלום, במה אפשר לעזור?")])
    evs = chat(client, "שלום")
    assert evs[0][0] == "thread"
    uuid.UUID(evs[0][1]["thread_id"])
    text = "".join(d["text"] for k, d in evs if k == "token")
    assert text == "שלום, במה אפשר לעזור?"
    assert evs[-1][0] == "done"


def test_tool_step_then_card_then_answer(data, cfg):
    script = [call("calculate", employee_args(data, "E-001")), AIMessage(content="הנטו עולה")]
    client, _, _ = make(data, cfg, script=script)
    evs = chat(client, "שאלה")
    k = kinds(evs)
    assert k.index("step") < k.index("card") < k.index("token") < k.index("done")
    step = next(d for kind, d in evs if kind == "step")
    assert step == {"tool": "calculate", "label": cfg["texts"]["steps"]["calculate"]}
    card = next(d for kind, d in evs if kind == "card")
    assert card["status"] == "ok"
    assert abs(card["card"]["diff"]["net"] - data.reference["E-001"]["diff"]) <= 1


def test_all_models_failing_gives_a_friendly_error(data, cfg):
    client, _, _ = make(data, cfg, model=Overloaded(messages=iter([])))
    evs = chat(client, "שלום")
    assert evs[-1] == ("error", {"message": cfg["texts"]["overloaded"]})
    assert "Traceback" not in json.dumps(evs, ensure_ascii=False)


def test_conversation_continues_and_can_be_restored(data, cfg):
    script = [AIMessage(content="מה העיסוק שלך?"), call("calculate", employee_args(data, "E-001")),
              AIMessage(content="הנטו עולה")]
    client, _, _ = make(data, cfg, script=script)
    tid = chat(client, "שאלה")[0][1]["thread_id"]
    evs = chat(client, "מנהלת מוצר", thread_id=tid)
    assert "thread" not in kinds(evs)  # same conversation

    state = client.get(f"/chat/{tid}").json()
    assert [(m["role"], m["text"]) for m in state["messages"]] == [
        ("user", "שאלה"), ("assistant", "מה העיסוק שלך?"), ("user", "מנהלת מוצר"), ("assistant", "הנטו עולה")]
    assert len(state["cards"]) == 1 and state["cards"][0]["status"] == "ok"


def test_bad_thread_id_is_rejected(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.post("/chat", json={"message": "x", "thread_id": "../etc"}).status_code == 422
    assert client.get("/chat/not-a-uuid").status_code == 422


def test_unknown_conversation_is_404(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.get(f"/chat/{uuid.uuid4()}").status_code == 404


# --- rep screen -------------------------------------------------------------------


def rachel_script(data):
    args = dict(employee_args(data, "E-003"), alternative_car="ATTO 2", alternative_car_year=2025)
    return args, [
        call("ask_rep", {"fields": ["carGroup", "companyCost", "participation"], "question": "BYD Atto 2?",
                         "car": "ATTO 2", "registration_year": 2025}, 0),
        call("calculate", args, 1),
        AIMessage(content="שלחתי שאלה לנציג התחבורה, והחלופה תתעדכן"),
    ]


def test_rep_needs_the_passcode(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.get("/rep/requests").status_code == 401
    assert client.get("/rep/requests", headers={"X-Rep-Passcode": "wrong"}).status_code == 401
    assert client.get("/rep/requests", headers={"X-Rep-Passcode": PASS}).status_code == 200


def test_rep_closed_when_no_passcode_configured(data, cfg):
    client, _, _ = make(data, cfg, script=[], passcode=None)
    assert client.get("/rep/requests", headers={"X-Rep-Passcode": ""}).status_code == 503


def test_rep_sees_question_with_employee_card_and_answers(data, cfg):
    _, script = rachel_script(data)
    client, queue, notifier = make(data, cfg, script=script)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    h = {"X-Rep-Passcode": PASS}

    [req] = client.get("/rep/requests", headers=h).json()
    assert req["thread_id"] == tid
    assert req["fields"] == ["carGroup", "companyCost", "participation"]
    assert req["card"]["today"]["values"]["net"]["value"] == data.reference["E-003"]["netToday"]

    r = client.post(f"/rep/requests/{req['id']}/answer", headers=h,
                    json={"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}})
    assert r.status_code == 200
    assert queue.pending(tid) == []
    assert notifier.sent == [(tid, {"type": "rep_answered", "request_id": req["id"]})]
    assert client.get("/rep/requests", headers=h).json() == []


def test_polling_fallback_shows_answered_requests(data, cfg):
    _, script = rachel_script(data)
    client, queue, _ = make(data, cfg, script=script)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    assert client.get(f"/chat/{tid}/rep").json() == {"pending": 1, "answered": []}
    rid = queue.pending(tid)[0]["id"]
    client.post(f"/rep/requests/{rid}/answer", headers={"X-Rep-Passcode": PASS},
                json={"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}})
    assert client.get(f"/chat/{tid}/rep").json() == {"pending": 0, "answered": [rid]}


def test_answer_unknown_request_is_404(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    r = client.post("/rep/requests/999/answer", headers={"X-Rep-Passcode": PASS}, json={"values": {"x": 1}})
    assert r.status_code == 404


def test_rep_answered_reruns_the_agent_with_the_system_note(data, cfg):
    args, script = rachel_script(data)
    script += [call("calculate", args, 2), AIMessage(content="הנטו יורד")]
    client, queue, _ = make(data, cfg, script=script)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    rid = queue.pending(tid)[0]["id"]
    client.post(f"/rep/requests/{rid}/answer", headers={"X-Rep-Passcode": PASS},
                json={"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}})

    r = client.post(f"/chat/{tid}/rep-answered")
    evs = events(r)
    card = next(d for k, d in evs if k == "card")
    assert card["status"] == "ok"
    assert evs[-1][0] == "done"

    restored = client.get(f"/chat/{tid}").json()["messages"]
    assert {"role": "system", "text": cfg["texts"]["repAnswered"]} in restored
