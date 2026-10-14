"""Monthly net-salary engine. Pure functions: same input -> same output.

Every rate, bracket and threshold is read from strauss-rules.json (netMethod)
or config/calc-assumptions.json. The order of the steps lives here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class NetBreakdown:
    salary: float  # base + commission + bonus
    maintenance: float
    electric_gross: float
    cash_gross: float
    value_of_use: float
    taxable: float
    tax_before_credits: float
    credit_points_value: float
    pension_credit: float
    tax: float
    national_insurance: float
    health: float
    pension: float
    keren: float
    participation: float
    family_share: float
    net: float

    @property
    def social(self) -> float:
        return self.national_insurance + self.health


def _bracket_tax(amount: float, brackets: list) -> float:
    tax, prev = 0.0, 0.0
    for ceiling, rate in brackets:
        top = amount if ceiling is None else min(amount, ceiling)
        if top > prev:
            tax += (top - prev) * rate
        if ceiling is None or amount <= ceiling:
            break
        prev = ceiling
    return tax


def _two_tier(amount: float, spec: dict) -> float:
    capped = min(amount, spec["ceiling"])
    low = min(capped, spec["threshold"])
    high = max(0.0, capped - spec["threshold"])
    return low * spec["lowRate"] + high * spec["highRate"]


def _components(emp, names: list[str]) -> float:
    values = {"base": emp.base, "commission": emp.commission, "bonus": emp.bonus}
    return sum(values[n] for n in names)


def _calc(emp, scenario, rules: dict, assumptions: dict, electric_gross: float) -> NetBreakdown:
    nm = rules["netMethod"]
    salary = emp.base + emp.commission + emp.bonus
    maintenance = scenario.maintenance
    cash = salary + maintenance + electric_gross

    taxable = cash + scenario.value_of_use
    if not rules["waiver"]["maintenanceIsTaxable"]:
        taxable -= maintenance
    if assumptions["participationReducesTaxable"]:
        taxable -= scenario.participation

    pension_base = _components(emp, assumptions["pensionBaseComponents"])
    keren_base = _components(emp, assumptions["kerenBaseComponents"])
    if rules["waiver"]["maintenanceIsPensionable"]:
        pension_base += maintenance

    tax_before = _bracket_tax(taxable, nm["brackets"])
    points_value = emp.credit_points * nm["creditPointValue"]
    pc = nm["pensionCredit"]
    pension_credit = pc["rate"] * assumptions["pensionCreditPct"] * min(pension_base, pc["incomeCeiling"])
    tax = max(0.0, tax_before - points_value - pension_credit)

    ni = _two_tier(taxable, nm["nationalInsurance"])
    health = _two_tier(taxable, nm["health"])
    pension = pension_base * emp.pension_pct / 100
    keren = keren_base * emp.keren_pct / 100

    net = cash - tax - ni - health - pension - keren - scenario.participation - scenario.family_share
    return NetBreakdown(
        salary=salary,
        maintenance=maintenance,
        electric_gross=electric_gross,
        cash_gross=cash,
        value_of_use=scenario.value_of_use,
        taxable=taxable,
        tax_before_credits=tax_before,
        credit_points_value=points_value,
        pension_credit=pension_credit,
        tax=tax,
        national_insurance=ni,
        health=health,
        pension=pension,
        keren=keren,
        participation=scenario.participation,
        family_share=scenario.family_share,
        net=net,
    )


def electric_gross_up(emp, scenario, rules: dict, assumptions: dict) -> float:
    """Smallest gross amount that raises net by exactly netBonus (bisection), then rounded."""
    target = rules["electric"]["netBonus"]
    base_scenario = replace(scenario, electric=False)
    base_net = _calc(emp, base_scenario, rules, assumptions, 0.0).net
    lo, hi = 0.0, target * 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _calc(emp, base_scenario, rules, assumptions, mid).net - base_net < target:
            lo = mid
        else:
            hi = mid
    rounding = assumptions.get("electricGrossUpRounding", "none")
    if rounding == "ceil":
        return float(math.ceil(hi - 1e-9))
    if rounding == "round":
        return float(math.floor(hi + 0.5))
    return hi


def compute_net(emp, scenario, rules: dict, assumptions: dict) -> NetBreakdown:
    gross = electric_gross_up(emp, scenario, rules, assumptions) if scenario.electric else 0.0
    return _calc(emp, scenario, rules, assumptions, gross)
