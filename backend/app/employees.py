"""Who the logged-in employee is: login id -> name (dummy names only).

The login id is the one in EMPLOYEE_CODES (app/auth.py). For a pilot, Strauss SSO replaces the
code, and the name comes from it; this table stays the place the screen reads it from.
The seed is config/employees.json; app/db.py has the Postgres version behind the same methods
(tests/test_employees_repository.py runs on both).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Optional


def load_seed(base_dir: Path) -> dict[str, str]:
    raw = json.loads((Path(base_dir) / "config" / "employees.json").read_text(encoding="utf-8"))
    return dict(raw["employees"])


class InMemoryEmployees:
    def __init__(self, seed: Mapping[str, str]):
        self._names = dict(seed)

    def name(self, employee_id: str) -> Optional[str]:
        return self._names.get(employee_id)
