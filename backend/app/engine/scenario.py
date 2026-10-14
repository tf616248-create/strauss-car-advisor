"""Turns 'what the employee has / asks about' into engine inputs, with eligibility.

Never guesses: an unknown car or a missing participation comes back in `missing`.
All thresholds come from strauss-rules.json and the Excel sheets.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass(frozen=True)
class EmployeeInput:
    occupation: str
    group: str
    base: float
    commission: float
    bonus: float
    pension_pct: float
    keren_pct: float
    credit_points: float
    children: int


@dataclass(frozen=True)
class Choice:
    kind: str  # "car" | "family_car" | "waiver"
    car_ref: Optional[str] = None  # catalog id or commercial name
    participation: Optional[float] = None  # stated / approved amount, else catalog default
    maintenance: Optional[float] = None  # waiver only, else occupation table

    @classmethod
    def car(cls, name, participation=None):
        return cls("car", car_ref=name, participation=participation)

    @classmethod
    def family_car(cls, name, participation=None):
        return cls("family_car", car_ref=name, participation=participation)

    @classmethod
    def waiver(cls, maintenance=None):
        return cls("waiver", maintenance=maintenance)



@dataclass(frozen=True)
class Scenario:
    label: str
    value_of_use: float
    participation: float
    maintenance: float
    electric: bool
    family_share: float
    car_id: Optional[str] = None

    def without_electric(self) -> "Scenario":
        return replace(self, electric=False)


@dataclass
class ScenarioResult:
    eligible: bool
    scenario: Optional[Scenario] = None
    reason_code: Optional[str] = None
    details: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _group_rank(rules: dict, group: str) -> int:
    return rules["groupOrder"].index(group)


def _waiver(emp: EmployeeInput, choice: Choice, data, is_current: bool) -> ScenarioResult:
    occ = data.occupations.get(emp.occupation)
    if occ is None:
        return ScenarioResult(eligible=False, reason_code="unknown_occupation", missing=["occupation"])
    if not is_current and not occ["waiverAllowed"]:
        return ScenarioResult(
            eligible=False, reason_code="waiver_not_allowed", details={"occupation": emp.occupation}
        )
    maintenance = choice.maintenance if choice.maintenance is not None else occ["maintenance"]
    return ScenarioResult(
        eligible=True,
        reason_code="waiver_allowed",
        details={"maintenance": maintenance},
        scenario=Scenario(
            label="waiver",
            value_of_use=0,
            participation=0,
            maintenance=maintenance,
            electric=False,
            family_share=0,
        ),
    )


def _car(emp: EmployeeInput, choice: Choice, data, is_current: bool) -> ScenarioResult:
    rules = data.rules
    excel = data.excel_values
    family_cars = rules["familyTrack"]["cars"]

    car = data.find_car(choice.car_ref or "")
    if car is None:
        return ScenarioResult(
            eligible=False, reason_code="car_not_in_catalog", missing=["car"], details={"car": choice.car_ref}
        )

    is_family_car = car["id"] in family_cars
    details = {"carGroup": car["group"], "employeeGroup": emp.group}

    if not is_current:
        if choice.kind == "car":
            if is_family_car:
                return ScenarioResult(eligible=False, reason_code="family_track_only", details=details)
            if _group_rank(rules, car["group"]) > _group_rank(rules, emp.group):
                return ScenarioResult(eligible=False, reason_code="group_too_high", details=details)
        elif choice.kind == "family_car":
            if not is_family_car:
                return ScenarioResult(eligible=False, reason_code="not_family_track_car", details=details)
            min_children = rules["familyTrack"]["minChildren"]
            details["minChildren"] = min_children
            details["children"] = emp.children
            if emp.children < min_children:
                return ScenarioResult(eligible=False, reason_code="not_enough_children", details=details)

    participation = (
        choice.participation if choice.participation is not None else car.get("defaultParticipation")
    )
    if participation is None:
        return ScenarioResult(
            eligible=True, reason_code="eligible", details=details, missing=["participation"]
        )

    family_share = 0.0
    if is_family_car:
        budget = rules["budgets"][emp.group]
        gap = max(0, car["companyCost"] - budget)
        family_share = gap * rules["familyTrack"]["gapSplitEmployee"]
        details.update({"budget": budget, "carCost": car["companyCost"], "gap": gap})

    return ScenarioResult(
        eligible=True,
        reason_code="family_track" if is_family_car else "own_group_or_lower",
        details=details,
        scenario=Scenario(
            label=f'{car["name"]} ({car["registrationYear"]})',
            value_of_use=car["valueOfUse"],
            participation=participation,
            maintenance=0,
            electric=car["drive"] == excel["electricDrive"],
            family_share=family_share,
            car_id=car["id"],
        ),
    )


def build_scenario(emp: EmployeeInput, choice: Choice, data, is_current: bool = False) -> ScenarioResult:
    """is_current=True describes what the employee has today (no eligibility check)."""
    if choice.kind == "waiver":
        return _waiver(emp, choice, data, is_current)
    if choice.kind in ("car", "family_car"):
        return _car(emp, choice, data, is_current)
    raise ValueError(f"unknown choice kind: {choice.kind}")
