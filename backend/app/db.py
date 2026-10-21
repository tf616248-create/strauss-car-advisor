"""Postgres (Neon): the connection pool, the rep queue, the employees' conversation list,
the employees' names and profiles, the payslips, and LangGraph's checkpointer.

Used only when DATABASE_URL is set; without it everything stays in memory.

- check=ConnectionPool.check_connection: Neon scales to zero and drops idle
  connections; a dead one is replaced before it is handed out.
- autocommit=True, prepare_threshold=0, dict rows: what PostgresSaver requires
  (prepare_threshold=0 also keeps Neon's pooler, PgBouncer, happy).
"""
from __future__ import annotations

from typing import Mapping, Optional

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.profile import PROFILE_FIELDS, check_source, tidy

SCHEMA = """
create table if not exists rep_requests (
    id          bigserial primary key,
    thread_id   text not null,
    fields      jsonb not null,
    question    text not null,
    car_key     text,
    answer      jsonb,
    created_at  timestamptz not null default now(),
    answered_at timestamptz,
    delivered_at timestamptz
);
create index if not exists rep_requests_open on rep_requests (thread_id) where answer is null;
"""

COLUMNS = "id::text as id, thread_id, fields, question, car_key, answer"


def make_pool(database_url: str, max_size: int = 5) -> ConnectionPool:
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
        open=True,
    )


def make_checkpointer(pool: ConnectionPool):
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver(pool)
    saver.setup()
    return saver


def _id(request_id: str) -> Optional[int]:
    return int(request_id) if str(request_id).isdigit() else None


class PostgresRepQueue:
    """Same methods and behaviour as InMemoryRepQueue (see tests/test_rep_repository.py)."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as conn:
            for statement in SCHEMA.split(";"):  # one command per execute (psycopg's extended protocol)
                if statement.strip():
                    conn.execute(statement)

    def _all(self, sql: str, params=()) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def add(self, thread_id: str, fields: list[str], question: str, car_key: Optional[str] = None) -> dict:
        """Add a request, or return the pending one already asking the same thing."""
        for req in self.pending(thread_id):
            if req["car_key"] == car_key and set(fields) <= set(req["fields"]):
                return req
        [req] = self._all(
            f"insert into rep_requests (thread_id, fields, question, car_key) values (%s, %s, %s, %s) "
            f"returning {COLUMNS}",
            (thread_id, Jsonb(list(fields)), question, car_key),
        )
        return req

    def get(self, request_id: str) -> Optional[dict]:
        rid = _id(request_id)
        if rid is None:
            return None
        rows = self._all(f"select {COLUMNS} from rep_requests where id = %s", (rid,))
        return rows[0] if rows else None

    def all_pending(self) -> list[dict]:
        return self._all(f"select {COLUMNS} from rep_requests where answer is null order by id")

    def pending(self, thread_id: str) -> list[dict]:
        return self._all(f"select {COLUMNS} from rep_requests where thread_id = %s and answer is null order by id",
                         (thread_id,))

    def answer(self, request_id: str, values: dict) -> None:
        rid = _id(request_id)
        rows = [] if rid is None else self._all(
            "update rep_requests set answer = %s, answered_at = now() where id = %s returning id",
            (Jsonb(dict(values)), rid),
        )
        if not rows:
            raise KeyError(request_id)

    def answers(self, thread_id: str) -> dict[tuple[str, Optional[str]], object]:
        """(field, car_key) -> value for every answered request in the conversation."""
        out = {}
        for req in self._all("select car_key, answer from rep_requests where thread_id = %s and answer is not null "
                             "order by id", (thread_id,)):
            for field, value in req["answer"].items():
                out[(field, req["car_key"])] = value
        return out

    def pending_fields(self, thread_id: str) -> set[tuple[str, Optional[str]]]:
        return {(f, r["car_key"]) for r in self.pending(thread_id) for f in r["fields"]}

    def new_answers(self, thread_id: str) -> int:
        [row] = self._all("select count(*) as n from rep_requests "
                          "where thread_id = %s and answer is not null and delivered_at is null", (thread_id,))
        return row["n"]

    def take_new_answers(self, thread_id: str) -> list[str]:
        """One update: two tabs asking at once still get each answer only once."""
        rows = self._all("update rep_requests set delivered_at = now() "
                         "where thread_id = %s and answer is not null and delivered_at is null "
                         "returning id::text as id", (thread_id,))
        return sorted((r["id"] for r in rows), key=int)

    def delete_threads(self, thread_ids: list[str]) -> None:
        """For tests: remove throwaway conversations."""
        if thread_ids:
            with self.pool.connection() as conn:
                conn.execute("delete from rep_requests where thread_id = any(%s)", (list(thread_ids),))


THREADS_SCHEMA = """
create table if not exists employee_threads (
    thread_id   text primary key,
    employee_id text not null,
    title       text,
    updated_at  timestamptz not null default clock_timestamp()
);
create index if not exists employee_threads_list on employee_threads (employee_id, updated_at desc);
"""


class PostgresThreads:
    """Same methods and behaviour as InMemoryThreads (see tests/test_threads_repository.py)."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as conn:
            for statement in THREADS_SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)

    def _all(self, sql: str, params=()) -> list[dict]:
        with self.pool.connection() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def add(self, employee_id: str, thread_id: str) -> None:
        self._all("insert into employee_threads (thread_id, employee_id) values (%s, %s) "
                  "on conflict (thread_id) do nothing", (thread_id, employee_id))

    def owner(self, thread_id: str) -> Optional[str]:
        rows = self._all("select employee_id from employee_threads where thread_id = %s", (thread_id,))
        return rows[0]["employee_id"] if rows else None

    def touch(self, thread_id: str, title: Optional[str]) -> None:
        # clock_timestamp(), not now(): with autocommit each statement is its own transaction anyway,
        # but this keeps two quick changes in order
        self._all("update employee_threads set title = %s, updated_at = clock_timestamp() where thread_id = %s",
                  (title, thread_id))

    def delete(self, thread_id: str) -> None:
        """The conversation's payslip goes with it (payslips: on delete cascade)."""
        self._all("delete from employee_threads where thread_id = %s", (thread_id,))

    def list(self, employee_id: str, limit: int = 50) -> list[dict]:
        rows = self._all("select thread_id, title, updated_at from employee_threads where employee_id = %s "
                         "order by updated_at desc limit %s", (employee_id, limit))
        return [{**r, "updated_at": r["updated_at"].isoformat()} for r in rows]

    def delete_threads(self, thread_ids: list[str]) -> None:
        """For tests: remove throwaway conversations."""
        if thread_ids:
            self._all("delete from employee_threads where thread_id = any(%s)", (list(thread_ids),))


EMPLOYEES_SCHEMA = """
create table if not exists employees (
    employee_id text primary key,
    name        text not null
);
"""


class PostgresEmployees:
    """Same methods as app/employees.InMemoryEmployees. setup() adds the seed's employees that
    are missing; a name already in the table stays (the table is the source)."""

    def __init__(self, pool: ConnectionPool, seed: Mapping[str, str]):
        self.pool = pool
        self._seed = dict(seed)

    def setup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(EMPLOYEES_SCHEMA)
            for employee_id, name in self._seed.items():
                conn.execute("insert into employees (employee_id, name) values (%s, %s) "
                             "on conflict (employee_id) do nothing", (employee_id, name))

    def name(self, employee_id: str) -> Optional[str]:
        with self.pool.connection() as conn:
            row = conn.execute("select name from employees where employee_id = %s", (employee_id,)).fetchone()
        return row["name"] if row else None

    def delete(self, employee_ids: list[str]) -> None:
        """For tests: remove throwaway employees."""
        with self.pool.connection() as conn:
            conn.execute("delete from employees where employee_id = any(%s)", (list(employee_ids),))


PROFILE_SCHEMA = """
create table if not exists employee_profile (
    employee_id           text primary key references employees (employee_id) on delete cascade,
    occupation            text,
    base                  double precision,
    commission            double precision,
    bonus                 double precision,
    pension_pct           double precision,
    keren_pct             double precision,
    credit_points         double precision,
    children              integer,
    current_kind          text,
    current_car           text,
    current_car_year      integer,
    current_participation double precision,
    sources               jsonb not null default '{}'::jsonb,
    updated_at            timestamptz not null default clock_timestamp()
);
alter table employee_profile add column if not exists sources jsonb not null default '{}'::jsonb;
alter table employee_profile add column if not exists theme text;
alter table employee_profile add column if not exists tone text;
"""


class PostgresProfiles:
    """Same methods as app/profile.InMemoryProfiles. A column per field (no group: it is computed from
    the occupation). Set up after employees (the foreign key)."""

    def __init__(self, pool: ConnectionPool, defaults: Optional[Mapping] = None):
        """defaults: the settings an employee has before choosing (agent.json settings.defaults)."""
        self.pool = pool
        self._defaults = dict(defaults or {})

    def settings(self, employee_id: str) -> dict:
        """theme and tone, kept with the profile; a setting never chosen is its default."""
        with self.pool.connection() as conn:
            row = conn.execute("select theme, tone from employee_profile where employee_id = %s",
                               (employee_id,)).fetchone()
        chosen = {k: v for k, v in (row or {}).items() if v is not None}
        return {**self._defaults, **chosen}

    def update_settings(self, employee_id: str, values: Mapping) -> None:
        """Checked already (validate_settings); the column names are fixed here, never from the request."""
        fields = [f for f in ("theme", "tone") if f in values]
        if not fields:
            return
        cols = ", ".join(fields)
        marks = ", ".join(["%s"] * len(fields))
        sets = ", ".join(f"{f} = excluded.{f}" for f in fields)
        with self.pool.connection() as conn:
            conn.execute(f"insert into employee_profile (employee_id, {cols}) values (%s, {marks}) "
                         f"on conflict (employee_id) do update set {sets}, updated_at = clock_timestamp()",
                         (employee_id, *(values[f] for f in fields)))

    def setup(self) -> None:
        with self.pool.connection() as conn:
            for statement in PROFILE_SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)

    def get(self, employee_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute("select * from employee_profile where employee_id = %s", (employee_id,)).fetchone()
        return tidy(row or {})

    def sources(self, employee_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute("select sources from employee_profile where employee_id = %s",
                               (employee_id,)).fetchone()
        return dict(row["sources"]) if row else {}

    def update(self, employee_id: str, values: Mapping, source: str = "profile") -> None:
        """Only these fields (the column names come from PROFILE_FIELDS, never from the request).
        Each set field gets this source; a cleared one loses its source."""
        check_source(source)
        fields = [f for f in PROFILE_FIELDS if f in values]
        if not fields:
            return
        added = {f: source for f in fields if values[f] is not None}
        cleared = [f for f in fields if values[f] is None]
        cols = ", ".join(fields)
        marks = ", ".join(["%s"] * len(fields))
        sets = ", ".join(f"{f} = excluded.{f}" for f in fields)
        with self.pool.connection() as conn:
            conn.execute(f"insert into employee_profile (employee_id, {cols}, sources) values (%s, {marks}, %s) "
                         f"on conflict (employee_id) do update set {sets}, "
                         f"sources = (employee_profile.sources || %s) - %s::text[], updated_at = clock_timestamp()",
                         (employee_id, *(values[f] for f in fields), Jsonb(added), Jsonb(added), cleared))


PAYSLIPS_SCHEMA = """
create table if not exists payslips (
    thread_id  text primary key references employee_threads (thread_id) on delete cascade,
    image      bytea,
    source     text not null,
    fields     jsonb,
    created_at timestamptz not null default now()
);
"""


class PostgresPayslips:
    """Same methods and behaviour as app/payslip.InMemoryPayslips (see tests/test_payslip_repository.py).
    One per conversation; set up after employee_threads (the foreign key)."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(PAYSLIPS_SCHEMA)

    def _all(self, sql: str, params=()) -> list[dict]:
        with self.pool.connection() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def save(self, thread_id: str, image: Optional[bytes], source: str) -> None:
        self._all("insert into payslips (thread_id, image, source) values (%s, %s, %s) "
                  "on conflict (thread_id) do update set image = excluded.image, source = excluded.source, "
                  "fields = null, created_at = now()", (thread_id, image, source))

    def set_fields(self, thread_id: str, fields: dict) -> None:
        self._all("update payslips set fields = %s where thread_id = %s", (Jsonb(dict(fields)), thread_id))

    def get(self, thread_id: str) -> Optional[dict]:
        rows = self._all("select image, source, fields, created_at from payslips where thread_id = %s", (thread_id,))
        if not rows:
            return None
        row = rows[0]
        return {**row, "image": None if row["image"] is None else bytes(row["image"]),
                "created_at": row["created_at"].isoformat()}

    def delete(self, thread_id: str) -> None:
        self._all("delete from payslips where thread_id = %s", (thread_id,))
