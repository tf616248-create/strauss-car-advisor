"""Payslip upload through the API: the file, the extraction (once), the agent carrying on with the values,
restore, delete, and the fixed messages when it can't be read. Fake models only."""
import json

import pytest
from langchain_core.messages import AIMessage

from app import payslip
from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.common import messages_of
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.payslip import InMemoryPayslips, PayslipReader
from tests import payslip_fixture as dummy
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args
from tests.test_agent_graph import ScriptedModel, call
from tests.test_api import chat, events, kinds
from tests.test_payslip import Broken, reader_model


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def make(data, cfg, script, image_model=None, text_model=None, employee="E01"):
    payslips = InMemoryPayslips()
    auth = make_auth()
    app = create_app(data=data, model=ScriptedModel(messages=iter(script)), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode="x", employee_auth=auth,
                     payslips=payslips, payslip_reader=PayslipReader(image_model, text_model, cfg))
    return authed(app, auth, employee), payslips, app, auth


def upload(client, tid, raw, content_type):
    return client.post(f"/chat/{tid}/payslip", content=raw, headers={"Content-Type": content_type})


def calc_args(data):
    """What the model passes after the payslip: no salary fields - the tool fills them from the payslip."""
    args = employee_args(data, "E-001")
    for f in dummy.FOUND:
        args.pop(f, None)
    args["bonus"] = 0
    args["keren_pct"] = 0
    return args


def script_after_upload(data):
    return [AIMessage(content="אפשר לענות על השאלות או להעלות תלוש"),  # the first question
            call("calculate", calc_args(data), 1),
            AIMessage(content="לקחתי מהתלוש: שכר בסיס 12,000. הנטו עולה")]


def start(client):
    return chat(client, "מה יקרה לנטו אם אעבור לחשמלי?")[0][1]["thread_id"]


def test_upload_reads_once_and_kobi_carries_on(data, cfg):
    image_model = reader_model()
    client, payslips, app, _ = make(data, cfg, script_after_upload(data), image_model=image_model)
    tid = start(client)

    evs = events(upload(client, tid, dummy.png(), "image/png"))
    assert kinds(evs)[0] == "step"
    found = next(d for k, d in evs if k == "payslip")
    assert found == {"status": "ok", "fields": dummy.FOUND}
    card = next(d for k, d in evs if k == "card")["card"]
    src = cfg["texts"]["sources"]["payslip"]
    assert card["your_data"]["base"] == {"value": 12000, "source": src}
    assert card["your_data"]["credit_points"] == {"value": 2.25, "source": src}
    assert "לקחתי מהתלוש" in "".join(d["text"] for k, d in evs if k == "token")
    assert evs[-1][0] == "done"

    assert len(image_model.seen) == 1  # the model saw the image once
    stored = payslips.get(tid)
    assert payslip.sniff(stored["image"]) == "jpeg" and stored["fields"] == dummy.FOUND


def test_the_image_is_not_in_the_conversation(data, cfg):
    client, _, app, _ = make(data, cfg, script_after_upload(data), image_model=reader_model())
    tid = start(client)
    upload(client, tid, dummy.jpeg(), "image/jpeg")
    raw = json.dumps(client.get(f"/chat/{tid}").json(), ensure_ascii=False)
    assert "base64" not in raw and "image_url" not in raw
    # the agent's history (sent to the model with every later message) holds only the note with the values
    msgs = messages_of(app.state.agent, tid)
    assert all(isinstance(m.content, str) for m in msgs)
    notes = [m for m in msgs if "kobi_payslip" in m.additional_kwargs]
    assert len(notes) == 1 and notes[0].content.startswith(cfg["texts"]["payslip"]["notePrefix"])


def test_restore_brings_the_payslip_back(data, cfg):
    client, _, _, _ = make(data, cfg, script_after_upload(data), image_model=reader_model())
    tid = start(client)
    upload(client, tid, dummy.pdf(), "application/pdf")
    restored = client.get(f"/chat/{tid}").json()
    assert restored["payslip"] == {"source": "image", "fields": dummy.FOUND, "image": f"/chat/{tid}/payslip"}
    assert {"role": "payslip", "text": cfg["texts"]["payslip"]["shown"]} in restored["messages"]
    img = client.get(f"/chat/{tid}/payslip")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert payslip.sniff(img.content) == "jpeg" and len(img.content) <= cfg["payslip"]["storeTargetBytes"]


def test_no_payslip_restores_as_none(data, cfg):
    client, _, _, _ = make(data, cfg, [AIMessage(content="שלום")])
    tid = start(client)
    assert client.get(f"/chat/{tid}").json()["payslip"] is None
    assert client.get(f"/chat/{tid}/payslip").status_code == 404


def test_deleting_the_conversation_deletes_the_payslip(data, cfg):
    client, payslips, _, _ = make(data, cfg, script_after_upload(data), image_model=reader_model())
    tid = start(client)
    upload(client, tid, dummy.png(), "image/png")
    assert client.delete(f"/chat/{tid}").status_code == 204
    assert payslips.get(tid) is None
    assert client.get(f"/chat/{tid}").status_code == 404
    assert tid not in [t["thread_id"] for t in client.get("/threads").json()["threads"]]


def test_pasted_text_goes_through_the_same_extraction(data, cfg):
    text_model = reader_model()
    client, payslips, _, _ = make(data, cfg, script_after_upload(data), text_model=text_model)
    tid = start(client)
    evs = events(client.post(f"/chat/{tid}/payslip-text", json={"text": "שכר יסוד 12,000.00 נקודות זיכוי 2.25"}))
    assert next(d for k, d in evs if k == "payslip")["fields"] == dummy.FOUND
    assert next(d for k, d in evs if k == "card")["status"] == "ok"
    assert payslips.get(tid)["source"] == "text" and payslips.get(tid)["image"] is None
    restored = client.get(f"/chat/{tid}").json()
    assert restored["payslip"]["image"] is None
    assert {"role": "payslip", "text": cfg["texts"]["payslip"]["shownText"]} in restored["messages"]
    assert "שכר יסוד 12,000.00" not in json.dumps(restored, ensure_ascii=False)  # the pasted text is not kept


@pytest.mark.parametrize("image_model, text_key", [(None, "noVision"), (Broken(messages=iter([])), "failed"),
                                                    ("empty", "failed")])
def test_cannot_read_gives_the_fixed_message_and_the_questions_go_on(data, cfg, image_model, text_key):
    if image_model == "empty":
        image_model = reader_model("{}")
    # the script has only the first answer: a model call after the upload would fail the test
    client, payslips, _, _ = make(data, cfg, [AIMessage(content="מה השכר שלך?")], image_model=image_model)
    tid = start(client)
    evs = events(upload(client, tid, dummy.png(), "image/png"))
    text = cfg["texts"]["payslip"][text_key]
    assert next(d for k, d in evs if k == "payslip")["status"] == ("no_vision" if text_key == "noVision" else "failed")
    assert "".join(d["text"] for k, d in evs if k == "token") == text
    assert "card" not in kinds(evs) and evs[-1][0] == "done"
    restored = client.get(f"/chat/{tid}").json()["messages"]
    assert restored[-1] == {"role": "assistant", "text": text}
    assert payslips.get(tid)["image"] is not None  # kept with the conversation all the same


@pytest.mark.parametrize("raw, content_type, status, key", [
    (b"GIF89a" + b"x" * 100, "image/gif", 415, "badType"),
    (b"not an image", "image/png", 415, "badType"),
    (b"\x89PNG\r\n\x1a\nbroken", "image/png", 422, "unreadable"),
])
def test_bad_files(data, cfg, raw, content_type, status, key):
    client, payslips, _, _ = make(data, cfg, [AIMessage(content="שלום")], image_model=reader_model())
    tid = start(client)
    r = upload(client, tid, raw, content_type)
    assert r.status_code == status and r.json()["detail"] == cfg["texts"]["payslip"][key]
    assert payslips.get(tid) is None


def test_too_large(data, cfg):
    client, payslips, _, _ = make(data, cfg, [AIMessage(content="שלום")], image_model=reader_model())
    tid = start(client)
    r = upload(client, tid, dummy.png() + b"\0" * cfg["payslip"]["maxBytes"], "image/png")
    assert r.status_code == 413 and r.json()["detail"] == cfg["texts"]["payslip"]["tooLarge"]
    assert payslips.get(tid) is None


def test_someone_elses_conversation_is_404(data, cfg):
    client, _, app, auth = make(data, cfg, [AIMessage(content="שלום")], image_model=reader_model())
    tid = start(client)
    other = authed(app, auth, "E02")
    assert upload(other, tid, dummy.png(), "image/png").status_code == 404
    assert other.post(f"/chat/{tid}/payslip-text", json={"text": "x"}).status_code == 404
    assert other.get(f"/chat/{tid}/payslip").status_code == 404
    assert other.delete(f"/chat/{tid}").status_code == 404


def test_needs_login(data, cfg):
    _, _, app, _ = make(data, cfg, [], image_model=reader_model())
    from fastapi.testclient import TestClient
    tid = "00000000-0000-0000-0000-000000000000"
    assert TestClient(app).post(f"/chat/{tid}/payslip", content=dummy.png(),
                                headers={"Content-Type": "image/png"}).status_code == 401


def test_langsmith_gets_only_payslip_uploaded(data, cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(payslip, "trace_upload", lambda *args: seen.append(args))
    client, _, _, _ = make(data, cfg, script_after_upload(data), image_model=reader_model())
    tid = start(client)
    upload(client, tid, dummy.png(), "image/png")
    assert seen == [(tid, "image", "ok", sorted(dummy.FOUND))]  # names only: no image, no values
