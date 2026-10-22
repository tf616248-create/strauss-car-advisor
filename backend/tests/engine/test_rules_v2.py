"""Rules v2: every calculation detail is read from strauss-rules.json.

Expected values are derived from the rules file, never typed here.
"""
import copy
from dataclasses import replace
from pathlib import Path

import pytest

from app.data.loader import check_family_track
from app.engine.net import compute_net
from app.engine.scenario import Choice, build_scenario
from tests.test_reference_employees import employee_input

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_no_separate_assumptions_file(data):
    assert not (BACKEND_DIR / "config" / "calc-assumptions.json").exists()
    assert not hasattr(data, "assumptions")


# --- pension credit: a ceiling, not a fixed 7% ---------------------------------


def _expected_credit(rules, pension_base, pension_pct):
    pc = rules["netMethod"]["pensionCredit"]
    contribution = pension_base * pension_pct / 100
    cap = pc["maxContributionRate"] * min(pension_base, pc["incomeCeiling"])
    return pc["rate"] * min(contribution, cap)


def _waiver_today(data, emp):
    return build_scenario(emp, Choice.waiver(), data, is_current=True).scenario


def test_pension_credit_ceiling_binds_for_reference_employees(data):
    pc = data.rules["netMethod"]["pensionCredit"]
    ceiling_credit = pc["rate"] * pc["maxContributionRate"] * pc["incomeCeiling"]
    for emp_id, row in data.employees.items():
        emp = employee_input(row)
        res = compute_net(emp, _waiver_today(data, emp), data.rules)
        assert res.pension_credit == pytest.approx(ceiling_credit), emp_id


def test_pension_credit_uses_actual_contribution_below_ceiling(data):
    # Low earner: 6% of 8,000 = 480 < 7% of 8,000 = 560 -> credit on 480, not 560
    emp = replace(employee_input(data.employees["E-001"]), base=8000, commission=0, bonus=0, pension_pct=6)
    res = compute_net(emp, _waiver_today(data, emp), data.rules)
    assert res.pension_credit == pytest.approx(_expected_credit(data.rules, 8000, 6))
    pc = data.rules["netMethod"]["pensionCredit"]
    assert res.pension_credit < pc["rate"] * pc["maxContributionRate"] * 8000


def test_pension_credit_capped_by_rate_when_contributing_more(data):
    # 8% of 8,000 = 640 > 7% of 8,000 = 560 -> credit on 560
    emp = replace(employee_input(data.employees["E-001"]), base=8000, commission=0, bonus=0, pension_pct=8)
    res = compute_net(emp, _waiver_today(data, emp), data.rules)
    assert res.pension_credit == pytest.approx(_expected_credit(data.rules, 8000, 8))


# --- contributions on the full gross ---------------------------------------------


def test_contributions_on_full_gross(data):
    emp = employee_input(data.employees["E-001"])
    res = compute_net(emp, _waiver_today(data, emp), data.rules)
    gross = emp.base + emp.commission + emp.bonus
    assert res.pension == pytest.approx(gross * emp.pension_pct / 100)
    assert res.keren == pytest.approx(gross * emp.keren_pct / 100)


# --- participation: net deduction only -------------------------------------------


def test_participation_does_not_change_taxable(data):
    emp = employee_input(data.employees["E-004"])
    with_p = build_scenario(emp, Choice.car("TUCSON", participation=400), data, is_current=True).scenario
    no_p = replace(with_p, participation=0)
    a = compute_net(emp, with_p, data.rules)
    b = compute_net(emp, no_p, data.rules)
    assert a.taxable == b.taxable
    assert b.net - a.net == pytest.approx(400)


# --- family track: the car list in the rules decides -----------------------------


def test_family_cars_come_from_rules_list(data):
    rules = copy.deepcopy(data.rules)
    rules["familyTrack"]["cars"] = ["CAR-20"]  # Carnival no longer on the list
    patched = replace(data, rules=rules)
    emp = employee_input(data.employees["E-002"])
    assert build_scenario(emp, Choice.family_car("SANTA FE"), patched).eligible
    res = build_scenario(emp, Choice.family_car("CARNIVAL"), patched)
    assert not res.eligible
    assert res.reason_code == "not_family_track_car"


def test_family_car_cost_from_catalog(data):
    emp = employee_input(data.employees["E-002"])
    budget = data.rules["budgets"][emp.group]
    split = data.rules["familyTrack"]["gapSplitEmployee"]
    for car_id in data.rules["familyTrack"]["cars"]:
        car = data.catalog[car_id]
        res = build_scenario(emp, Choice.family_car(car_id), data)
        assert res.scenario.family_share == pytest.approx(max(0, car["companyCost"] - budget) * split)


def test_family_track_matches_catalog(data):
    check_family_track(data.rules, data.catalog, data.excel_values["familyGroup"])


def test_family_track_mismatch_fails_loudly(data):
    rules = copy.deepcopy(data.rules)
    rules["familyTrack"]["cars"] = ["CAR-19"]
    with pytest.raises(ValueError, match="CAR-20"):
        check_family_track(rules, data.catalog, data.excel_values["familyGroup"])
    rules["familyTrack"]["cars"] = ["CAR-19", "CAR-20", "CAR-99"]
    with pytest.raises(ValueError, match="CAR-99"):
        check_family_track(rules, data.catalog, data.excel_values["familyGroup"])


# --- unknown rule values are refused, not guessed --------------------------------


@pytest.mark.parametrize(
    "path, value",
    [
        (("netMethod", "rounding", "during"), "shekel"),
        (("netMethod", "contributionsBase"), "base_only"),
        (("netMethod", "participation", "treatment"), "gross_deduction"),
    ],
)
def test_unsupported_rule_value_raises(data, path, value):
    rules = copy.deepcopy(data.rules)
    node = rules
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    emp = employee_input(data.employees["E-001"])
    alt = build_scenario(emp, Choice.car("ATTO 3"), data).scenario
    with pytest.raises(ValueError):
        compute_net(emp, alt, rules)
