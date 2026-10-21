"""Contract: the employees table (login id -> name). In memory and in Postgres.

The names are dummy names (config/employees.json). Postgres runs only when DATABASE_URL is set,
on throwaway ids that are deleted at the end.
"""
import os
import uuid

import pytest
from dotenv import load_dotenv

from app.employees import InMemoryEmployees, load_seed
from tests.conftest import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest.fixture
def emp():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(params=["memory", "postgres"])
def make_store(request):
    """make_store(seed) -> a store seeded with these names."""
    if request.param == "memory":
        yield InMemoryEmployees
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresEmployees, make_pool

    pool = make_pool(DATABASE_URL)
    made = []

    def make(seed):
        store = PostgresEmployees(pool, seed)
        store.setup()
        made.extend(seed)
        return store
    yield make
    if made:
        PostgresEmployees(pool, {}).delete(made)
    pool.close()


def test_name_of_a_seeded_employee(make_store, emp):
    store = make_store({emp: "עובדת דמה"})
    assert store.name(emp) == "עובדת דמה"


def test_unknown_employee_has_no_name(make_store, emp):
    store = make_store({})
    assert store.name(emp) is None


def test_seeding_again_keeps_the_name_in_the_table(make_store, emp):
    """The table is the source; the seed only fills in employees that are missing.
    (Postgres only: in memory each store is its own table.)"""
    if make_store is InMemoryEmployees:
        pytest.skip("in memory there is no shared table")
    make_store({emp: "שם ראשון"})
    store = make_store({emp: "שם אחר"})
    assert store.name(emp) == "שם ראשון"


def test_the_seed_file_has_dummy_names_for_every_demo_login():
    seed = load_seed(BACKEND_DIR)
    assert set(seed) == {f"E{i:02d}" for i in range(1, 11)}  # EMPLOYEE_CODES: E01..E10
    assert all(isinstance(n, str) and n.strip() for n in seed.values())
