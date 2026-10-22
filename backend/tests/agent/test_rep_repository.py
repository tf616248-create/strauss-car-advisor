"""Contract: the in-memory rep queue and the Postgres (Neon) one behave the same.

The same tests run on both. Postgres runs only when DATABASE_URL is set (backend/.env),
on throwaway conversation ids that are deleted at the end.
"""
import os
import uuid

import pytest
from dotenv import load_dotenv

from app.agent.rep_queue import InMemoryRepQueue
from tests.conftest import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def pg_pool():
    from app.db import make_pool

    pool = make_pool(DATABASE_URL)
    yield pool
    pool.close()


@pytest.fixture(params=["memory", "postgres"])
def queue(request):
    if request.param == "memory":
        yield InMemoryRepQueue()
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresRepQueue

    q = PostgresRepQueue(request.getfixturevalue("pg_pool"))
    q.setup()
    q.created_threads = []
    yield q
    q.delete_threads(q.created_threads)


@pytest.fixture
def new_tid(queue):
    def make():
        tid = str(uuid.uuid4())
        getattr(queue, "created_threads", []).append(tid)
        return tid
    return make


def test_add_and_get(queue, new_tid):
    tid = new_tid()
    req = queue.add(tid, ["carGroup", "companyCost"], "BYD Atto 2?", "01014/00045/2025")
    assert isinstance(req["id"], str)
    assert req["thread_id"] == tid
    assert req["fields"] == ["carGroup", "companyCost"]
    assert req["question"] == "BYD Atto 2?"
    assert req["car_key"] == "01014/00045/2025"
    assert req["answer"] is None
    assert queue.get(req["id"]) == req


def test_same_open_question_is_not_asked_twice(queue, new_tid):
    tid = new_tid()
    first = queue.add(tid, ["carGroup", "companyCost"], "q", "car-1")
    assert queue.add(tid, ["carGroup"], "q again", "car-1")["id"] == first["id"]
    assert queue.add(tid, ["carGroup"], "other car", "car-2")["id"] != first["id"]
    assert queue.add(tid, ["group"], "no car", None)["id"] != first["id"]


def test_pending_is_per_conversation(queue, new_tid):
    a, b = new_tid(), new_tid()
    ra = queue.add(a, ["group"], "qa")
    rb = queue.add(b, ["group"], "qb")
    assert [r["id"] for r in queue.pending(a)] == [ra["id"]]
    ours = {r["id"] for r in queue.all_pending() if r["thread_id"] in (a, b)}
    assert ours == {ra["id"], rb["id"]}


def test_answer_closes_the_request_and_keeps_value_types(queue, new_tid):
    tid = new_tid()
    req = queue.add(tid, ["carGroup", "companyCost"], "q", "car-1")
    assert queue.pending_fields(tid) == {("carGroup", "car-1"), ("companyCost", "car-1")}
    queue.answer(req["id"], {"carGroup": "ב", "companyCost": 3500})
    assert queue.pending(tid) == []
    assert queue.pending_fields(tid) == set()
    assert queue.answers(tid) == {("carGroup", "car-1"): "ב", ("companyCost", "car-1"): 3500}
    assert queue.get(req["id"])["answer"] == {"carGroup": "ב", "companyCost": 3500}
    assert req["id"] not in {r["id"] for r in queue.all_pending()}


def test_unknown_request(queue):
    assert queue.get("999999999") is None
    assert queue.get("not-a-number") is None
    with pytest.raises(KeyError):
        queue.answer("999999999", {"x": 1})


def test_new_answers_are_handed_over_once(queue, new_tid):
    """The bot recalculates once per rep answer, even after a reload or from a second tab."""
    tid = new_tid()
    r1 = queue.add(tid, ["carGroup"], "q1", "car-1")
    queue.add(tid, ["group"], "q2", None)
    assert queue.new_answers(tid) == 0
    queue.answer(r1["id"], {"carGroup": "ב"})
    assert queue.new_answers(tid) == 1
    assert queue.take_new_answers(tid) == [r1["id"]]
    assert queue.new_answers(tid) == 0
    assert queue.take_new_answers(tid) == []


def test_startup_is_safe_to_repeat(pg_pool):
    """Every Render restart runs the table setup and PostgresSaver.setup() again."""
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresRepQueue, make_checkpointer

    for _ in range(2):
        PostgresRepQueue(pg_pool).setup()
        make_checkpointer(pg_pool)
