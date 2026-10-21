"""The employee's profile: the details calculate needs from the employee, kept per employee.

- PROFILE_FIELDS: the employee's fields of calculate, without the group. The group is never kept:
  it comes from the occupation (OccupationMatcher, the sheet "עיסוקים").
- validate(): the same checks for the profile endpoint and for the tools (ranges in agent.json).
- InMemoryProfiles here; app/db.py has PostgresProfiles (table employee_profile, linked to employees)
  behind the same methods (tests/test_profile.py runs on both).
- The tools fill the profile's values in, in code (app/agent/advisor.py), like the payslip's: the model
  never passes them, and never sees them in the prompt - only which fields are there (profile_section).
- LangSmith: trace_profile sends the field names, never the values.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from itertools import product
from typing import Mapping, Optional

from langsmith import traceable

PROFILE_FIELDS = ("occupation", "base", "commission", "bonus", "pension_pct", "keren_pct", "credit_points",
                  "children", "current_kind", "current_car", "current_car_year", "current_participation")
INT_FIELDS = ("children", "current_car_year")
CURRENT_KINDS = ("car", "waiver")
# asked only in some questions: the family track, or a car outside the catalog
OPTIONAL_FIELDS = ("children", "current_car_year")

_NIQQUD = re.compile("[֑-ׇ]")
_PUNCT = re.compile(r"[^\w\s/]")


def _words(text: str) -> list[str]:
    text = _NIQQUD.sub("", unicodedata.normalize("NFC", str(text)))
    return _PUNCT.sub(" ", text).replace("_", " ").split()


def _forms(word: str) -> list[str]:
    """'מנהל/ת' -> ['מנהל', 'מנהלת'], 'אנליסט/ית' -> ['אנליסט', 'אנליסטית']: the sheet's own two forms."""
    stem, sep, suffix = word.partition("/")
    return [stem, stem + suffix] if sep else [word]


class OccupationMatcher:
    """The occupation as the employee wrote it -> the occupation in the sheet, and its group.
    Forgiving about the wording: spaces, punctuation, ה הידיעה, and the masculine and feminine forms the
    sheet itself gives ('מנהל/ת'). Never a guess: anything else is not_found, with the closest ones."""

    def __init__(self, occupations: Mapping[str, dict], max_suggestions: int = 3):
        self.occupations = occupations
        self.max_suggestions = max_suggestions
        self._variants: dict[tuple[str, ...], str] = {}
        for name in occupations:
            for combo in product(*(_forms(w) for w in _words(name))):
                self._variants.setdefault(combo, name)
        self._vocab = {w for combo in self._variants for w in combo}

    def _query(self, text: str) -> tuple[str, ...]:
        out = []
        for w in _words(text):
            w = w.replace("/", "")
            if w not in self._vocab and w.startswith("ה") and w[1:] in self._vocab:
                w = w[1:]  # ה הידיעה: "משאבי האנוש", "נהג ההפצה"
            out.append(w)
        return tuple(out)

    def find(self, text: str) -> dict:
        query = self._query(text or "")
        name = self._variants.get(query) if query else None
        if name:
            return {"status": "ok", "occupation": name, "group": self.occupations[name]["group"]}
        return {"status": "not_found", "suggestions": self.suggest(query)}

    def suggest(self, query: tuple[str, ...]) -> list[str]:
        joined = " ".join(query)
        scores = {}
        for combo, name in self._variants.items():
            overlap = len(set(query) & set(combo)) / len(combo)
            score = SequenceMatcher(None, joined, " ".join(combo)).ratio() + overlap / 2
            scores[name] = max(scores.get(name, 0), score)
        ranked = sorted(scores, key=lambda n: -scores[n])[: self.max_suggestions]
        # 2-3: the third only when it is about as close as the first
        if len(ranked) > 2 and scores[ranked[2]] < 0.6 * scores[ranked[0]]:
            ranked = ranked[:2]
        return ranked


def _number(field: str, value, cfg: dict):
    """The value as a number inside its range, or None."""
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    lo, hi = cfg["ranges"][field]
    if not lo <= x <= hi:
        return None
    if field in INT_FIELDS:
        return int(x) if x.is_integer() else None
    return int(x) if x.is_integer() else x


def validate(values: Mapping, cfg: dict, matcher: OccupationMatcher) -> tuple[dict, dict]:
    """(clean values, {field: why not}). None clears a field. No group: it is computed, not kept."""
    clean, bad = {}, {}
    for field, value in values.items():
        if field not in PROFILE_FIELDS:
            bad[field] = {"reason": "unknown_field"}
        elif value is None:
            clean[field] = None
        elif field == "occupation":
            found = matcher.find(value)
            if found["status"] == "ok":
                clean[field] = found["occupation"]
            else:
                bad[field] = {"suggestions": found["suggestions"]}
        elif field == "current_kind":
            if value in CURRENT_KINDS:
                clean[field] = value
            else:
                bad[field] = {"options": list(CURRENT_KINDS)}
        elif field == "current_car":
            if str(value).strip():
                clean[field] = str(value).strip()
            else:
                bad[field] = {"reason": "empty"}
        else:
            x = _number(field, value, cfg)
            if x is None:
                bad[field] = {"range": cfg["ranges"][field]}
            else:
                clean[field] = x
    return clean, bad


def tidy(row: Mapping) -> dict:
    """Only the fields that are set; whole numbers as ints (as the employee wrote them)."""
    out = {}
    for field in PROFILE_FIELDS:
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        out[field] = value
    return out


def missing_for_prompt(fields: Mapping) -> list[str]:
    """What the profile lacks for a regular question (children and the car's year only in some)."""
    needed = [f for f in PROFILE_FIELDS if f not in OPTIONAL_FIELDS]
    if fields.get("current_kind") == "waiver":
        needed = [f for f in needed if f not in ("current_car", "current_participation")]
    return [f for f in needed if f not in fields]


@traceable(name="profile", run_type="chain")
def trace_profile(event: str, fields: list[str]) -> dict:
    """The profile's only LangSmith trace: which fields were read or updated - never their values."""
    return {"event": event, "fields": list(fields)}


class InMemoryProfiles:
    def __init__(self):
        self._rows: dict[str, dict] = {}

    def get(self, employee_id: str) -> dict:
        return tidy(self._rows.get(employee_id, {}))

    def update(self, employee_id: str, values: Mapping) -> None:
        """Only these fields; the others stay. None clears one. The latest value wins."""
        row = self._rows.setdefault(employee_id, {})
        for field, value in values.items():
            if value is None:
                row.pop(field, None)
            else:
                row[field] = value


def group_of(fields: Mapping, occupations: Mapping[str, dict]) -> Optional[str]:
    occupation = fields.get("occupation")
    return occupations[occupation]["group"] if occupation in occupations else None
