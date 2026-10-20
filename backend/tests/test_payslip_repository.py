"""Contract: the payslip kept with a conversation. In memory and in Postgres.

Postgres runs only when DATABASE_URL is set, on throwaway ids that are deleted at the end.
"""
import os
import uuid

import pytest
from dotenv import load_dotenv

from app.payslip import InMemoryPayslips
from app.threads import InMemoryThreads
from tests.conftest import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")
JPEG = b"\xff\xd8\xff" + b"x" * 1000


@pytest.fixture(scope="module")
def pg_pool():
    from app.db import make_pool

    pool = make_pool(DATABASE_URL)
    yield pool
    pool.close()


@pytest.fixture(params=["memory", "postgres"])
def stores(request):
    """(threads, payslips): a payslip belongs to a conversation in the list."""
    if request.param == "memory":
        yield InMemoryThreads(), InMemoryPayslips()
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresPayslips, PostgresThreads

    pool = request.getfixturevalue("pg_pool")
    threads, payslips = PostgresThreads(pool), PostgresPayslips(pool)
    threads.setup()
    payslips.setup()
    threads.created = []
    yield threads, payslips
    threads.delete_threads(threads.created)


@pytest.fixture
def tid(stores):
    threads, _ = stores
    t = str(uuid.uuid4())
    getattr(threads, "created", []).append(t)
    threads.add(f"test-{uuid.uuid4().hex[:8]}", t)
    return t


def test_nothing_until_uploaded(stores, tid):
    assert stores[1].get(tid) is None


def test_saved_with_the_conversation(stores, tid):
    _, payslips = stores
    payslips.save(tid, JPEG, "image")
    got = payslips.get(tid)
    assert bytes(got["image"]) == JPEG and got["source"] == "image" and got["fields"] is None


def test_fields_are_kept(stores, tid):
    _, payslips = stores
    payslips.save(tid, JPEG, "image")
    payslips.set_fields(tid, {"base": 12000, "credit_points": 2.25})
    assert payslips.get(tid)["fields"] == {"base": 12000, "credit_points": 2.25}


def test_pasted_text_keeps_no_image(stores, tid):
    _, payslips = stores
    payslips.save(tid, None, "text")
    got = payslips.get(tid)
    assert got["image"] is None and got["source"] == "text"


def test_a_second_upload_replaces_the_first(stores, tid):
    _, payslips = stores
    payslips.save(tid, JPEG, "image")
    payslips.set_fields(tid, {"base": 9000})
    payslips.save(tid, JPEG + b"2", "image")
    got = payslips.get(tid)
    assert bytes(got["image"]) == JPEG + b"2" and got["fields"] is None


def test_deleted(stores, tid):
    _, payslips = stores
    payslips.save(tid, JPEG, "image")
    payslips.delete(tid)
    assert payslips.get(tid) is None


def test_deleting_the_conversation_deletes_the_payslip(stores, tid):
    threads, payslips = stores
    payslips.save(tid, JPEG, "image")
    threads.delete(tid)
    payslips.delete(tid)  # the API does both (in Postgres the first one is enough: on delete cascade)
    assert threads.owner(tid) is None and payslips.get(tid) is None


def test_postgres_cascades_from_the_conversation(stores, tid):
    threads, payslips = stores
    if isinstance(payslips, InMemoryPayslips):
        pytest.skip("Postgres only")
    payslips.save(tid, JPEG, "image")
    threads.delete(tid)
    assert payslips.get(tid) is None
