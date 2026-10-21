"""The weekly usage limit per employee (app/usage_limit.py): every billed token counts (fallback models too),
a failed call and an eval run do not; the week starts on Sunday at 00:00, Israel time; at 0 the server
answers with the fixed message and calls no model; an answer that already started is never cut."""
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.payslip import InMemoryPayslips, PayslipReader
from app.usage_limit import InMemoryUsage, UsageMeter, week_start
from tests import payslip_fixture as dummy
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.test_agent_graph import ScriptedModel
from tests.test_api import events, kinds
from tests.test_payslip import reader_model

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")
UTC = timezone.utc


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


# --- the config -------------------------------------------------------------------------------

def test_the_limit_is_the_average_conversation_times_25(cfg):
    u = cfg["usage"]
    assert u["weekly_token_limit"] == u["avg_tokens_per_conversation"] * 25
    assert "usage.csv" in u["limitNote"] and "25" in u["limitNote"]
    assert u["timezone"] == "Asia/Jerusalem"
    assert u["supportEmail"] in cfg["texts"]["usage"]["limitReached"]
    assert "להחליף בכתובת אמיתית בפיילוט" in u["supportEmailNote"]


# --- the week: Sunday 00:00, Israel time ------------------------------------------------------

@pytest.mark.parametrize("now, sunday", [
    (utc(2026, 10, 24, 20, 59), "2026-10-18"),  # Saturday 23:59 in Israel (summer time, UTC+3)
    (utc(2026, 10, 24, 21, 0), "2026-10-25"),   # Sunday 00:00 in Israel - still Saturday in UTC
    (utc(2026, 10, 25, 12, 0), "2026-10-25"),   # Sunday noon (summer time ended at 02:00 that night)
    (utc(2026, 11, 28, 21, 59), "2026-11-22"),  # Saturday 23:59 in Israel (winter time, UTC+2)
    (utc(2026, 11, 28, 22, 0), "2026-11-29"),   # Sunday 00:00 in Israel
    (utc(2026, 11, 25, 9, 0), "2026-11-22"),    # a Wednesday
])
def test_the_week_starts_on_sunday_at_midnight_israel_time(cfg, now, sunday):
    assert week_start(now, cfg["usage"]["timezone"]).isoformat() == sunday


# --- the stores -------------------------------------------------------------------------------

@pytest.fixture(params=["memory", "postgres"])
def store(request):
    emp = f"test-{uuid.uuid4().hex[:8]}"
    if request.param == "memory":
        yield InMemoryUsage(), emp
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresEmployees, PostgresUsage, make_pool

    pool = make_pool(DATABASE_URL)
    employees = PostgresEmployees(pool, {emp: "עובד דמה", emp + "b": "עובד דמה ב"})
    employees.setup()
    usage = PostgresUsage(pool)
    usage.setup()
    yield usage, emp
    employees.delete([emp, emp + "b"])  # their usage goes with them (on delete cascade)
    pool.close()


def test_counts_add_up_within_the_week_and_start_again_on_sunday(store):
    usage, emp = store
    week, next_week = week_start(utc(2026, 11, 25), "Asia/Jerusalem"), week_start(utc(2026, 12, 2), "Asia/Jerusalem")
    assert usage.used(emp, week) == 0
    usage.add(emp, week, 1000)
    usage.add(emp, week, 234)
    assert usage.used(emp, week) == 1234
    assert usage.used(emp, next_week) == 0  # the reset: a new week, a new count
    assert usage.used(emp + "b", week) == 0  # per employee


# --- the meter: what counts -------------------------------------------------------------------

def ai(i, o, model="gemini"):
    return AIMessage(content="x", usage_metadata={"input_tokens": i, "output_tokens": o, "total_tokens": i + o},
                     response_metadata={"kobi_model": model})


@pytest.fixture
def meter(cfg):
    return UsageMeter(InMemoryUsage(), cfg, now=lambda: utc(2026, 11, 25, 9))


def test_every_billed_token_counts_fallback_models_too(meter):
    meter.record("E01", [ai(6000, 200), ai(7000, 300, model="groq"), HumanMessage(content="x")], {})
    assert meter.status("E01")["used"] == 13500


def test_a_failed_call_that_was_not_billed_does_not_count(meter):
    meter.record("E01", [AIMessage(content="")], {})  # no usage: the call failed, nothing was billed
    assert meter.status("E01")["used"] == 0


def test_an_eval_run_does_not_count(meter):
    meter.record("E01", [ai(6000, 200)], {"tags": ["eval"]})
    assert meter.status("E01")["used"] == 0


def test_the_status(meter, cfg):
    avg, limit = cfg["usage"]["avg_tokens_per_conversation"], cfg["usage"]["weekly_token_limit"]
    meter.record("E01", [ai(avg * 2, 0)], {})
    s = meter.status("E01")
    assert s["used"] == avg * 2 and s["limit"] == limit and s["remaining"] == limit - avg * 2
    assert s["conversations_left"] == 23 and s["blocked"] is False
    assert s["resets_on"] == "2026-11-29"  # the next Sunday
    meter.record("E01", [ai(limit, 0)], {})
    s = meter.status("E01")
    assert s["remaining"] == 0 and s["conversations_left"] == 0 and s["blocked"] is True


def test_conversations_left_rounds_down(meter, cfg):
    avg = cfg["usage"]["avg_tokens_per_conversation"]
    meter.record("E01", [ai(cfg["usage"]["weekly_token_limit"] - avg // 2, 0)], {})
    assert meter.status("E01")["conversations_left"] == 0  # half a conversation: "פחות משיחה אחת"
    assert meter.status("E01")["blocked"] is False


# --- through the API --------------------------------------------------------------------------

class BilledModel(ScriptedModel):
    """The scripted model, with token usage on its last chunk (as the real providers stream it)."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        chunks = list(super()._stream(messages, stop, run_manager, **kwargs))
        for i, c in enumerate(chunks):
            if i == len(chunks) - 1:
                c = ChatGenerationChunk(message=AIMessageChunk(
                    content=c.message.content, tool_call_chunks=c.message.tool_call_chunks,
                    usage_metadata={"input_tokens": 6000, "output_tokens": 500, "total_tokens": 6500}))
            yield c


def make(data, cfg, script, image_model=None):
    usage = InMemoryUsage()
    auth = make_auth()
    model = BilledModel(messages=iter(script))
    app = create_app(data=data, model=model, rep_queue=InMemoryRepQueue(), notifier=InMemoryNotifier(), cfg=cfg,
                     rep_passcode="x", employee_auth=auth, usage=usage, payslips=InMemoryPayslips(),
                     payslip_reader=PayslipReader(image_model, None, cfg))
    return authed(app, auth), usage, app


def this_week(cfg):
    return week_start(datetime.now(UTC), cfg["usage"]["timezone"])


def test_a_question_is_counted_for_its_employee(data, cfg):
    client, usage, _ = make(data, cfg, [AIMessage(content="שלום לך")])
    evs = events(client.post("/chat", json={"message": "שלום"}))
    assert kinds(evs)[-1] == "done"
    assert usage.used("E01", this_week(cfg)) == 6500
    assert client.get("/usage").json()["used"] == 6500


def test_at_0_kobi_does_not_answer_and_no_model_is_called(data, cfg):
    client, usage, app = make(data, cfg, [])  # an empty script: a model call would fail
    usage.add("E01", this_week(cfg), cfg["usage"]["weekly_token_limit"])
    evs = events(client.post("/chat", json={"message": "שלום"}))
    assert kinds(evs) == ["limit", "done"]  # no new conversation that would stay empty
    limit = dict(evs)["limit"]
    assert limit["message"] == cfg["texts"]["usage"]["limitReached"]
    assert limit["email"] == cfg["usage"]["supportEmail"]
    assert "token" not in kinds(evs) and "error" not in kinds(evs)


def test_the_answer_that_started_is_not_cut_the_block_applies_from_the_next_message(data, cfg):
    words = "תשובה ארוכה שממשיכה עד הסוף"
    client, usage, _ = make(data, cfg, [AIMessage(content=words)])
    usage.add("E01", this_week(cfg), cfg["usage"]["weekly_token_limit"] - 1)  # one token left
    first = events(client.post("/chat", json={"message": "שלום"}))
    assert "".join(d["text"] for k, d in first if k == "token") == words  # all of it
    assert kinds(first)[-1] == "done"
    assert client.get("/usage").json()["blocked"] is True
    tid = first[0][1]["thread_id"]
    second = events(client.post("/chat", json={"message": "ועוד", "thread_id": tid}))
    assert "limit" in kinds(second) and "token" not in kinds(second)


def test_a_payslip_at_0_is_not_read(data, cfg):
    image_model = reader_model()
    client, usage, _ = make(data, cfg, [AIMessage(content="שלום")], image_model=image_model)
    tid = events(client.post("/chat", json={"message": "שלום"}))[0][1]["thread_id"]
    usage.add("E01", this_week(cfg), cfg["usage"]["weekly_token_limit"])
    evs = events(client.post(f"/chat/{tid}/payslip", content=dummy.png(), headers={"Content-Type": "image/png"}))
    assert "limit" in kinds(evs)
    assert image_model.seen == []  # the model never saw the payslip
    assert client.get(f"/chat/{tid}").json()["payslip"] is None  # and the file was not kept


def test_usage_needs_a_login(data, cfg):
    _, _, app = make(data, cfg, [])
    assert TestClient(app).get("/usage").status_code == 401


def test_the_usage_view(data, cfg):
    client, _, _ = make(data, cfg, [])
    view = client.get("/usage").json()
    assert set(view) == {"used", "limit", "remaining", "avg_tokens_per_conversation", "conversations_left",
                         "blocked", "resets_on"}
    assert view["limit"] == cfg["usage"]["weekly_token_limit"] and view["used"] == 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", view["resets_on"])
