"""Contract: whose conversation is it, and the employee's history list. In memory and in Postgres.

Postgres runs only when DATABASE_URL is set, on throwaway ids that are deleted at the end.
"""
import os
import time
import uuid

import pytest
from dotenv import load_dotenv

from app.threads import InMemoryThreads
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
def threads(request):
    if request.param == "memory":
        yield InMemoryThreads()
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresThreads

    store = PostgresThreads(request.getfixturevalue("pg_pool"))
    store.setup()
    store.created = []
    yield store
    store.delete_threads(store.created)


@pytest.fixture
def emp():
    return f"test-{uuid.uuid4().hex[:8]}"  # a throwaway employee, so Postgres rows never mix


@pytest.fixture
def new_tid(threads):
    def make():
        tid = str(uuid.uuid4())
        getattr(threads, "created", []).append(tid)
        return tid
    return make


def test_owner(threads, emp, new_tid):
    tid = new_tid()
    assert threads.owner(tid) is None
    threads.add(emp, tid)
    assert threads.owner(tid) == emp


def test_adding_twice_keeps_the_first_owner(threads, emp, new_tid):
    tid = new_tid()
    threads.add(emp, tid)
    threads.add("someone-else", tid)
    assert threads.owner(tid) == emp


def test_list_is_mine_only_newest_first(threads, emp, new_tid):
    a, b, c = new_tid(), new_tid(), new_tid()
    threads.add(emp, a)
    threads.touch(a, "ראשונה")
    time.sleep(0.01)
    threads.add(emp, b)
    threads.touch(b, "שנייה")
    threads.add("someone-else", c)
    listed = threads.list(emp)
    assert [(t["thread_id"], t["title"]) for t in listed] == [(b, "שנייה"), (a, "ראשונה")]
    assert all(isinstance(t["updated_at"], str) for t in listed)


def test_touch_moves_a_conversation_to_the_top(threads, emp, new_tid):
    a, b = new_tid(), new_tid()
    threads.add(emp, a)
    time.sleep(0.01)
    threads.add(emp, b)
    time.sleep(0.01)
    threads.touch(a, "חזרתי אליה")
    assert [t["thread_id"] for t in threads.list(emp)] == [a, b]


def test_a_new_conversation_has_no_title_yet(threads, emp, new_tid):
    tid = new_tid()
    threads.add(emp, tid)
    assert threads.list(emp)[0]["title"] is None


def test_delete(threads, emp, new_tid):
    a, b = new_tid(), new_tid()
    threads.add(emp, a)
    threads.add(emp, b)
    threads.delete(a)
    assert threads.owner(a) is None
    assert [t["thread_id"] for t in threads.list(emp)] == [b]
