"""The 6 sample employees from the challenge Excel.

Expected numbers are read from the 'חישובים' sheet - never typed here.
What the employee asks (today vs. alternative) mirrors the 'השאלה' column.
Tolerance: ±1 ₪ (the reference sheet rounds to whole shekels).
"""
import pytest

from app.engine.net import compute_net
from app.engine.scenario import Choice, EmployeeInput, build_scenario

TOL = 1

# employee id -> (today, alternative), as the employee would state it
CASES = {
    "E-001": (Choice.car("COROLLA CROSS", participation=300), Choice.car("ATTO 3")),
    "E-002": (Choice.car("NIRO", participation=250), Choice.family_car("CARNIVAL")),
    "E-003": (Choice.waiver(), Choice.car("MG4")),
    "E-004": (Choice.car("TUCSON", participation=400), Choice.car("EV3")),
    "E-005": (Choice.car("MAZDA 3", participation=350), Choice.waiver()),
    "E-006": (Choice.car("OCTAVIA", participation=500), Choice.car("MODEL 3")),
}
IDS = list(CASES)


def employee_input(row):
    return EmployeeInput(
        occupation=row["occupation"],
        group=row["group"],
        base=row["base"],
        commission=row["commission"],
        bonus=row["bonus"],
        pension_pct=row["pensionPct"],
        keren_pct=row["kerenPct"],
        credit_points=row["creditPoints"],
        children=row["children"],
    )


def run(data, emp_id):
    emp = employee_input(data.employees[emp_id])
    today_choice, alt_choice = CASES[emp_id]
    today = build_scenario(emp, today_choice, data, is_current=True)
    alt = build_scenario(emp, alt_choice, data)
    assert today.eligible and not today.missing, today
    assert alt.eligible and not alt.missing, alt
    net_today = compute_net(emp, today.scenario, data.rules)
    net_alt = compute_net(emp, alt.scenario, data.rules)
    return net_today, net_alt, alt


def test_all_six_employees_present(data):
    assert set(IDS) == set(data.reference) == set(data.employees)


@pytest.mark.parametrize("emp_id", IDS)
def test_net_today(data, emp_id):
    net_today, _, _ = run(data, emp_id)
    assert abs(round(net_today.net) - data.reference[emp_id]["netToday"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_net_alternative(data, emp_id):
    _, net_alt, _ = run(data, emp_id)
    assert abs(round(net_alt.net) - data.reference[emp_id]["netAlt"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_difference(data, emp_id):
    net_today, net_alt, _ = run(data, emp_id)
    diff = round(net_alt.net) - round(net_today.net)
    assert abs(diff - data.reference[emp_id]["diff"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_tax(data, emp_id):
    net_today, net_alt, _ = run(data, emp_id)
    ref = data.reference[emp_id]
    assert abs(round(net_today.tax) - ref["taxToday"]) <= TOL
    assert abs(round(net_alt.tax) - ref["taxAlt"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_national_insurance_and_health(data, emp_id):
    net_today, net_alt, _ = run(data, emp_id)
    ref = data.reference[emp_id]
    assert abs(round(net_today.social) - ref["socialToday"]) <= TOL
    assert abs(round(net_alt.social) - ref["socialAlt"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_electric_gross_up(data, emp_id):
    _, net_alt, _ = run(data, emp_id)
    assert abs(net_alt.electric_gross - data.reference[emp_id]["electricGross"]) <= TOL


@pytest.mark.parametrize("emp_id", IDS)
def test_electric_adds_250_net(data, emp_id):
    """No rounding during the calculation (rules v2), so the employee sees exactly +250 net."""
    emp = employee_input(data.employees[emp_id])
    _, alt_choice = CASES[emp_id]
    alt = build_scenario(emp, alt_choice, data)
    if not alt.scenario.electric:
        pytest.skip("not an electric alternative")
    with_bonus = compute_net(emp, alt.scenario, data.rules)
    without = compute_net(emp, alt.scenario.without_electric(), data.rules)
    assert abs(with_bonus.net - without.net - data.rules["electric"]["netBonus"]) <= 0.01


@pytest.mark.parametrize("emp_id", IDS)
def test_family_track_share(data, emp_id):
    _, net_alt, _ = run(data, emp_id)
    assert abs(net_alt.family_share - data.reference[emp_id]["familyShare"]) <= TOL
