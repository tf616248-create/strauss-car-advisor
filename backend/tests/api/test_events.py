"""The rep answered -> the employee's browser hears "changed" over SSE.

The database is the source of truth; SSE only rings. The event carries nothing:
the browser reads the current state from the server.
"""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier, conversation_events
from app.api.main import create_app
from app.threads import InMemoryThreads
from tests.auth_helpers import authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.agent.test_agent_graph import ScriptedModel
from tests.api.test_api import PASS, chat, rachel_script

ANSWER = {"values": {"carGroup": "ב", "companyCost": 3500, "participation": 250}}
H = {"X-Rep-Passcode": PASS}


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def fast(cfg, heartbeat=0.05):
    return dict(cfg, sseHeartbeatSeconds=heartbeat)


class SpyNotifier(InMemoryNotifier):
    def __init__(self, on_publish=None):
        super().__init__()
        self.published = []
        self.on_publish = on_publish

    def publish(self, conversation_id):
        if self.on_publish:
            self.on_publish(conversation_id)
        self.published.append(conversation_id)
        super().publish(conversation_id)


AUTH = make_auth()
TOKEN = AUTH.issue("E01")


def build(data, cfg, script=(), queue=None, notifier=None):
    queue = queue or InMemoryRepQueue()
    notifier = notifier or InMemoryNotifier()
    threads = InMemoryThreads()
    for tid in (TID_A, TID_B):  # the fixed ids below belong to the logged-in employee
        threads.add("E01", tid)
    app = create_app(data=data, model=ScriptedModel(messages=iter(list(script))), rep_queue=queue,
                     notifier=notifier, cfg=cfg, rep_passcode=PASS, employee_auth=AUTH, threads=threads)
    return app, queue, notifier


# --- the notifier -----------------------------------------------------------------


def test_publish_reaches_only_the_same_conversation():
    async def go():
        n = InMemoryNotifier()
        async with n.subscribe("a") as qa, n.subscribe("b") as qb:
            n.publish("a")
            assert await asyncio.wait_for(qa.get(), 1) == "changed"
            await asyncio.sleep(0.01)
            assert qb.empty()
    asyncio.run(go())


def test_publish_works_from_another_thread():
    """The rep's answer is handled in a worker thread, the SSE stream on the event loop."""
    async def go():
        n = InMemoryNotifier()
        async with n.subscribe("a") as qa:
            await asyncio.to_thread(n.publish, "a")
            assert await asyncio.wait_for(qa.get(), 1) == "changed"
    asyncio.run(go())


def test_leaving_removes_the_subscriber():
    async def go():
        n = InMemoryNotifier()
        async with n.subscribe("a"), n.subscribe("a"):
            assert n.subscriber_count("a") == 2
        assert n.subscriber_count("a") == 0
        n.publish("a")  # nobody listening - no error
    asyncio.run(go())


# --- the SSE stream ---------------------------------------------------------------


def test_stream_sends_changed_with_no_details():
    async def go():
        n = InMemoryNotifier()
        stream = conversation_events(n, "a", heartbeat=5)
        await asyncio.wait_for(anext(stream), 1)  # opening lines
        n.publish("a")
        chunk = await asyncio.wait_for(anext(stream), 1)
        assert chunk.startswith("event: changed\n")
        data = [line for line in chunk.splitlines() if line.startswith("data:")]
        assert data and json.loads(data[0][len("data:"):]) == {}
        await stream.aclose()
    asyncio.run(go())


def test_stream_sends_a_heartbeat_comment():
    async def go():
        stream = conversation_events(InMemoryNotifier(), "a", heartbeat=0.05)
        await asyncio.wait_for(anext(stream), 1)
        chunk = await asyncio.wait_for(anext(stream), 1)
        assert chunk.startswith(":")  # an SSE comment: keeps the connection alive, fires no event
        await stream.aclose()
    asyncio.run(go())


def test_closing_the_stream_removes_the_subscriber():
    async def go():
        n = InMemoryNotifier()
        stream = conversation_events(n, "a", heartbeat=5)
        await anext(stream)
        assert n.subscriber_count("a") == 1
        await stream.aclose()
        assert n.subscriber_count("a") == 0
    asyncio.run(go())


# --- GET /conversations/{id}/events over real ASGI ------------------------------------

TID_A = "11111111-1111-1111-1111-111111111111"
TID_B = "22222222-2222-2222-2222-222222222222"


class Browser:
    """An EventSource-like client: reads the stream chunk by chunk, can hang up."""

    def __init__(self, app, path, token=TOKEN):
        self.chunks: asyncio.Queue = asyncio.Queue()
        self.gone = asyncio.Event()
        self.status = None
        self._started = False
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": f"token={token}".encode(),  # EventSource can't send headers
            "root_path": "", "headers": [(b"host", b"test"), (b"accept", b"text/event-stream")],
            "client": ("test", 1), "server": ("test", 80),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self):
        if not self._started:
            self._started = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, msg):
        if self.gone.is_set():
            raise OSError("client gone")
        if msg["type"] == "http.response.start":
            self.status = msg["status"]
            self.headers = dict(msg["headers"])
        elif msg.get("body"):
            await self.chunks.put(msg["body"].decode())

    async def next(self, timeout=1.0):
        return await asyncio.wait_for(self.chunks.get(), timeout)

    async def wait_for(self, prefix, timeout=1.0):
        async def loop():
            while not (chunk := await self.chunks.get()).startswith(prefix):
                pass
            return chunk
        return await asyncio.wait_for(loop(), timeout)

    async def hang_up(self):
        self.gone.set()
        try:
            await asyncio.wait_for(self.task, 2)
        except ClientDisconnect:  # what uvicorn gets, and ignores, when the browser is gone
            pass


def test_events_endpoint_is_sse(data, cfg):
    async def go():
        app, _, _ = build(data, fast(cfg))
        b = Browser(app, f"/conversations/{TID_A}/events")
        await b.next()
        assert b.status == 200
        assert b.headers[b"content-type"].startswith(b"text/event-stream")
        await b.hang_up()
    asyncio.run(go())


def test_events_endpoint_rejects_a_bad_id(data, cfg):
    client = authed(build(data, cfg)[0], AUTH)
    assert client.get("/conversations/not-a-uuid/events").status_code == 422


def test_heartbeat_interval_comes_from_the_config(data, cfg):
    assert cfg["sseHeartbeatSeconds"] == 20

    async def go():
        app, _, _ = build(data, fast(cfg, heartbeat=0.05))
        b = Browser(app, f"/conversations/{TID_A}/events")
        await b.wait_for(":", timeout=1)  # well under the real 20s: the test value was used
        await b.hang_up()
    asyncio.run(go())


def test_disconnected_browser_is_removed(data, cfg):
    async def go():
        app, _, notifier = build(data, fast(cfg))
        b = Browser(app, f"/conversations/{TID_A}/events")
        await b.next()
        assert notifier.subscriber_count(TID_A) == 1
        await b.hang_up()
        assert notifier.subscriber_count(TID_A) == 0
    asyncio.run(go())


def test_rep_answer_rings_only_the_employee_of_that_conversation(data, cfg):
    _, script = rachel_script(data)

    async def go():
        app, queue, _ = build(data, fast(cfg, heartbeat=0.2), script=script)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                     headers={"Authorization": f"Bearer {TOKEN}"}) as http:
            r = await http.post("/chat", json={"message": "אם אקח Atto 2?"})
            tid = json.loads(r.text.split("data: ", 1)[1].split("\n", 1)[0])["thread_id"]
            mine = Browser(app, f"/conversations/{tid}/events")
            other = Browser(app, f"/conversations/{TID_B}/events")
            await mine.next()
            await other.next()

            rid = queue.pending(tid)[0]["id"]
            assert (await http.post(f"/rep/requests/{rid}/answer", headers=H, json=ANSWER)).status_code == 200

            assert (await mine.wait_for("event: changed")).startswith("event: changed")
            with pytest.raises(asyncio.TimeoutError):
                await other.wait_for("event: changed", timeout=0.3)
            await mine.hang_up()
            await other.hang_up()
    asyncio.run(go())


# --- rep answer: save first, ring after -------------------------------------------


def test_rep_answer_is_saved_before_the_ring(data, cfg):
    _, script = rachel_script(data)
    seen_at_ring = []
    queue = InMemoryRepQueue()
    notifier = SpyNotifier(on_publish=lambda tid: seen_at_ring.append(queue.pending(tid)))
    app, _, _ = build(data, cfg, script=script, queue=queue, notifier=notifier)
    client = authed(app, AUTH)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    rid = queue.pending(tid)[0]["id"]

    assert client.post(f"/rep/requests/{rid}/answer", headers=H, json=ANSWER).status_code == 200
    assert notifier.published == [tid]
    assert seen_at_ring == [[]]  # when the bell rang, the answer was already stored


class BrokenSave(InMemoryRepQueue):
    def answer(self, request_id, values):
        raise ConnectionError("database is down")


def test_failed_save_rings_nobody(data, cfg):
    _, script = rachel_script(data)
    queue, notifier = BrokenSave(), SpyNotifier()
    app, _, _ = build(data, cfg, script=script, queue=queue, notifier=notifier)
    client = authed(app, AUTH)
    tid = chat(client, "אם אקח Atto 2?")[0][1]["thread_id"]
    rid = queue.pending(tid)[0]["id"]

    r = client.post(f"/rep/requests/{rid}/answer", headers=H, json=ANSWER)
    assert r.status_code == 503
    assert notifier.published == []


# --- health does not touch the database ------------------------------------------


class DatabaseDown:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError("database is down")
        return fail


def test_health_answers_when_the_database_is_down(data, cfg):
    app, _, _ = build(data, cfg, queue=DatabaseDown())
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
