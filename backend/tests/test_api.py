"""FastAPI server: SSE chat, conversation restore, rep screen API. Scripted fake model."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args
from tests.test_agent_graph import ScriptedModel, call
from tests.test_agent_models import Hanging, Overloaded, _release_hanging_calls  # noqa: F401 (autouse)

PASS = "test-pass"


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


class RecordingNotifier(InMemoryNotifier):
    def __init__(self):
        super().__init__()
        self.published = []

    def publish(self, conversation_id):
        self.published.append(conversation_id)
        super().publish(conversation_id)


def make(data, cfg, script=None, model=None, passcode=PASS):
    queue, notifier = InMemoryRepQueue(), RecordingNotifier()
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


def test_hanging_models_switch_then_give_a_friendly_error(data, cfg):
    """A model that never answers must not leave the stream silent: switch, then an error event."""
    import time

    from app.agent.models import with_fallbacks

    first, second = Hanging(messages=iter([])), Hanging(messages=iter([]))
    client, _, _ = make(data, cfg, model=with_fallbacks([first, second], timeout_seconds=0.2))
    start = time.monotonic()
    evs = chat(client, "שלום")
    assert time.monotonic() - start < 3
    assert (first.calls, second.calls) == (1, 1)  # timed out on the first, moved on to the second
    assert evs[-1] == ("error", {"message": cfg["texts"]["overloaded"]})


def test_tokens_still_stream_after_switching_from_a_hanging_model(data, cfg):
    from app.agent.models import with_fallbacks

    backup = ScriptedModel(messages=iter([AIMessage(content="תשובה מהגיבוי")]))
    client, _, _ = make(data, cfg, model=with_fallbacks([Hanging(messages=iter([])), backup], timeout_seconds=0.2))
    evs = chat(client, "שלום")
    assert "".join(d["text"] for k, d in evs if k == "token") == "תשובה מהגיבוי"
    assert evs[-1][0] == "done"


# --- the clock counts until the first word only; an abandoned model stays silent ----------

import re
import time as _time

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk


class Paced(GenericFakeChatModel):
    """Streams its answer word by word: waits `first` seconds, then `between` seconds per word."""
    first: float = 0
    between: float = 0
    calls: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        msg = self._generate(messages, stop, run_manager, **kwargs).generations[0].message
        _time.sleep(self.first)
        for i, part in enumerate(p for p in re.split(r"(\s)", msg.content) if p):
            if i:
                _time.sleep(self.between)
            yield ChatGenerationChunk(message=AIMessageChunk(content=part))


def paced(text, first=0.0, between=0.0):
    return Paced(messages=iter([AIMessage(content=text)]), first=first, between=between)


def tokens(evs):
    return "".join(d["text"] for k, d in evs if k == "token")


def test_words_of_an_abandoned_model_never_reach_the_employee(data, cfg):
    """The bug seen live: three answers glued together, because timed-out models kept writing."""
    from app.agent.models import with_fallbacks

    # clock 0.5s. The late model writes at 0.6s, after it was abandoned. The backup starts at 0.5s
    # and writes at 0.9s, so the late words arrive while the backup is still thinking.
    late = paced("תשובה ישנה", first=0.6)
    backup = paced("תשובה חדשה", first=0.4)
    client, _, _ = make(data, cfg, model=with_fallbacks([late, backup], timeout_seconds=0.5))
    evs = chat(client, "שלום")
    assert tokens(evs) == "תשובה חדשה"
    assert evs[-1][0] == "done"


def test_a_model_that_is_writing_is_not_cut_off(data, cfg):
    """The clock counts until the first word; a slow writer finishes its answer."""
    from app.agent.models import with_fallbacks

    slow = paced("אחת שתיים שלוש ארבע", between=0.15)  # ~0.9s in total, more than the clock
    backup = paced("גיבוי")
    client, _, _ = make(data, cfg, model=with_fallbacks([slow, backup], timeout_seconds=0.3))
    evs = chat(client, "שלום")
    assert tokens(evs) == "אחת שתיים שלוש ארבע"
    assert backup.calls == 0
    assert evs[-1][0] == "done"


def test_a_model_that_stops_mid_answer_gives_an_error_not_a_second_answer(data, cfg):
    """Switching after words were shown would write a second answer below the first."""
    from app.agent.models import with_fallbacks

    stuck = paced("התחלה ואז שקט", between=1.5)
    backup = paced("גיבוי")
    client, _, _ = make(data, cfg, model=with_fallbacks([stuck, backup], timeout_seconds=0.3))
    evs = chat(client, "שלום")
    assert tokens(evs) == "התחלה"
    assert backup.calls == 0
    assert evs[-1] == ("error", {"message": cfg["texts"]["overloaded"]})


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
    assert notifier.published == [tid]
    assert client.get("/rep/requests", headers=h).json() == []


def test_restore_says_whether_the_rep_answered(data, cfg):
    """The browser reads the state from the server (after "changed", a reload, or returning to the tab)."""
    args, script = rachel_script(data)
    script += [call("calculate", args, 2), AIMessage(content="הנטו יורד")]
    client, queue, _ = make(data, cfg, script=script)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    assert client.get(f"/chat/{tid}").json()["rep"] == {"pending": 1, "new_answers": 0}
    rid = queue.pending(tid)[0]["id"]
    client.post(f"/rep/requests/{rid}/answer", headers={"X-Rep-Passcode": PASS},
                json={"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}})
    assert client.get(f"/chat/{tid}").json()["rep"] == {"pending": 0, "new_answers": 1}

    client.post(f"/chat/{tid}/rep-answered")  # the bot recalculates: the answer is handed over
    assert client.get(f"/chat/{tid}").json()["rep"] == {"pending": 0, "new_answers": 0}


def test_rep_answered_twice_runs_the_bot_once(data, cfg):
    """A second tab (or a late reload) asking again finds nothing new and does not rerun the bot."""
    args, script = rachel_script(data)
    script += [call("calculate", args, 2), AIMessage(content="הנטו יורד")]
    client, queue, _ = make(data, cfg, script=script)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    rid = queue.pending(tid)[0]["id"]
    client.post(f"/rep/requests/{rid}/answer", headers={"X-Rep-Passcode": PASS},
                json={"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}})
    assert "token" in kinds(events(client.post(f"/chat/{tid}/rep-answered")))
    assert kinds(events(client.post(f"/chat/{tid}/rep-answered"))) == ["done"]


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
