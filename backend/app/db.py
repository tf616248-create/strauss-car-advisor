"""Postgres (Neon): the connection pool, the rep queue, and LangGraph's checkpointer.

Used only when DATABASE_URL is set; without it everything stays in memory.

- check=ConnectionPool.check_connection: Neon scales to zero and drops idle
  connections; a dead one is replaced before it is handed out.
- autocommit=True, prepare_threshold=0, dict rows: what PostgresSaver requires
  (prepare_threshold=0 also keeps Neon's pooler, PgBouncer, happy).
"""
from __future__ import annotations

from typing import Optional

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

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
