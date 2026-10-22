"""Eligibility edge cases from stage 3. Rules come from the JSON / Excel only."""
from app.engine.scenario import Choice, build_scenario
from tests.engine.test_reference_employees import employee_input


def emp(data, emp_id):
    return employee_input(data.employees[emp_id])


def test_car_from_higher_group_not_eligible(data):
    # Rachel is group ב, Model 3 is group ד
    res = build_scenario(emp(data, "E-003"), Choice.car("MODEL 3"), data)
    assert not res.eligible
    assert res.reason_code == "group_too_high"


def test_car_from_lower_group_eligible(data):
    # Eli is group ד, Dolphin is group א
    res = build_scenario(emp(data, "E-006"), Choice.car("BYD DOLPHIN"), data)
    assert res.eligible


def test_family_track_needs_min_children(data):
    # Noa has 2 children
    res = build_scenario(emp(data, "E-001"), Choice.family_car("CARNIVAL"), data)
    assert not res.eligible
    assert res.reason_code == "not_enough_children"


def test_waiver_not_allowed_for_mandatory_car_occupation(data):
    # David is field sales - car is mandatory
    res = build_scenario(emp(data, "E-002"), Choice.waiver(), data)
    assert not res.eligible
    assert res.reason_code == "waiver_not_allowed"


def test_family_car_not_selectable_as_regular_car(data):
    res = build_scenario(emp(data, "E-006"), Choice.car("CARNIVAL"), data)
    assert not res.eligible
    assert res.reason_code == "family_track_only"


def test_unknown_car_returns_missing_not_guess(data):
    res = build_scenario(emp(data, "E-003"), Choice.car("ATTO 2"), data)
    assert res.scenario is None
    assert "car" in res.missing


def test_family_gap_share_uses_employee_group_budget(data):
    # David: group ב budget 3,700; Carnival 6,000 -> gap 2,300 -> 50% = 1,150
    res = build_scenario(emp(data, "E-002"), Choice.family_car("CARNIVAL"), data)
    assert res.scenario.family_share == 1150
