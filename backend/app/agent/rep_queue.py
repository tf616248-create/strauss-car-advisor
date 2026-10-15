"""The shared 'transport rep' queue.

The rep never talks to the employee; they only answer field questions.
In memory for tests and local development; app/db.py has the Postgres (Neon)
version behind the same methods (tests/test_rep_repository.py runs on both).
"""
from __future__ import annotations

import itertools
from typing import Optional


class InMemoryRepQueue:
    def __init__(self):
        self._requests: list[dict] = []
        self._ids = itertools.count(1)

    def add(self, thread_id: str, fields: list[str], question: str, car_key: Optional[str] = None) -> dict:
        """Add a request, or return the pending one already asking the same thing."""
        for req in self.pending(thread_id):
            if req["car_key"] == car_key and set(fields) <= set(req["fields"]):
                return req
        req = {
            "id": str(next(self._ids)),
            "thread_id": thread_id,
            "fields": list(fields),
            "question": question,
            "car_key": car_key,
            "answer": None,
            "delivered": False,
        }
        self._requests.append(req)
        return _public(req)

    def get(self, request_id: str) -> Optional[dict]:
        req = next((r for r in self._requests if r["id"] == request_id), None)
        return _public(req) if req else None

    def all_pending(self) -> list[dict]:
        return [_public(r) for r in self._requests if r["answer"] is None]

    def pending(self, thread_id: str) -> list[dict]:
        return [_public(r) for r in self._requests if r["thread_id"] == thread_id and r["answer"] is None]

    def answer(self, request_id: str, values: dict) -> None:
        for req in self._requests:
            if req["id"] == request_id:
                req["answer"] = dict(values)
                return
        raise KeyError(request_id)

    def answers(self, thread_id: str) -> dict[tuple[str, Optional[str]], object]:
        """(field, car_key) -> value for every answered request in the conversation."""
        out = {}
        for req in self._requests:
            if req["thread_id"] == thread_id and req["answer"] is not None:
                for field, value in req["answer"].items():
                    out[(field, req["car_key"])] = value
        return out

    def pending_fields(self, thread_id: str) -> set[tuple[str, Optional[str]]]:
        return {(f, r["car_key"]) for r in self.pending(thread_id) for f in r["fields"]}

    def _new(self, thread_id: str) -> list[dict]:
        return [r for r in self._requests
                if r["thread_id"] == thread_id and r["answer"] is not None and not r["delivered"]]

    def new_answers(self, thread_id: str) -> int:
        """Rep answers the bot has not recalculated with yet."""
        return len(self._new(thread_id))

    def take_new_answers(self, thread_id: str) -> list[str]:
        """Hand the new answers to the bot, once: a second call returns []."""
        new = self._new(thread_id)
        for r in new:
            r["delivered"] = True
        return [r["id"] for r in new]


def _public(req: dict) -> dict:
    return {k: v for k, v in req.items() if k != "delivered"}
