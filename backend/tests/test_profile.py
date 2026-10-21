"""The employee profile (app/profile.py): the occupation -> group lookup, the checks, the stores,
and how calculate uses it. No model here: the agent's side is in test_profile_agent.py."""
import os
import uuid

import pytest
from dotenv import load_dotenv

from app.agent.advisor import Advisor, load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.profile import PROFILE_FIELDS, InMemoryProfiles, OccupationMatcher, validate
from tests.conftest import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


@pytest.fixture(scope="module")
def matcher(data, cfg):
    return OccupationMatcher(data.occupations, cfg["profile"]["maxSuggestions"])


# --- the fields ------------------------------------------------------------------------------

def test_the_profile_has_every_employee_field_calculate_needs_and_no_group(cfg):
    calc_employee = [f for f in Advisor.CALCULATE_FIELDS if not f.startswith("alternative") and f != "group"]
    assert set(PROFILE_FIELDS) == set(calc_employee)
    assert "group" not in PROFILE_FIELDS
    assert list(cfg["profile"]["fields"]) == list(PROFILE_FIELDS)
    assert set(cfg["texts"]["profile"]["labels"]) == set(PROFILE_FIELDS)


# --- occupation_to_group -----------------------------------------------------------------------

@pytest.mark.parametrize("text, occupation", [
    ("מפתח/ת תוכנה", "מפתח/ת תוכנה"),           # as in the sheet
    ("  מפתח/ת    תוכנה ", "מפתח/ת תוכנה"),     # spaces
    ("מפתח תוכנה", "מפתח/ת תוכנה"),             # the masculine form
    ("מפתחת תוכנה", "מפתח/ת תוכנה"),            # the feminine form
    ("אנליסטית נתונים", "אנליסט/ית נתונים"),
    ("נציגת מכירות שטח", "נציג/ת מכירות שטח"),
    ("מנהלת משאבי האנוש", "מנהל/ת משאבי אנוש"),  # ה הידיעה
    ("נהג ההפצה", "נהג/ת הפצה"),
    ("המנהל מוצר", "מנהל/ת מוצר"),
    ("מנהל-מוצר", "מנהל/ת מוצר"),               # punctuation
])
def test_occupation_found_despite_the_wording(matcher, data, text, occupation):
    res = matcher.find(text)
    assert res == {"status": "ok", "occupation": occupation, "group": data.occupations[occupation]["group"]}


@pytest.mark.parametrize("text", ["שף", "מתכנת", "מנהל", "מפתח תכנה"])
def test_not_found_gives_2_or_3_close_suggestions_and_no_guess(matcher, data, text):
    res = matcher.find(text)
    assert res["status"] == "not_found"
    assert "group" not in res and "occupation" not in res
    assert 2 <= len(res["suggestions"]) <= 3
    assert all(s in data.occupations for s in res["suggestions"])


def test_suggestions_are_the_close_ones(matcher):
    assert matcher.find("מפתח תכנה")["suggestions"][0] == "מפתח/ת תוכנה"  # a typo: first, but not taken
    assert all("מנהל" in s for s in matcher.find("מנהל")["suggestions"])  # several managers: asks which


def test_empty_occupation_is_not_found(matcher):
    assert matcher.find("   ")["status"] == "not_found"


# --- the checks (the profile endpoint and the tools) ---------------------------------------------

def test_validate_takes_good_values_and_names_the_bad_ones(cfg, matcher):
    clean, bad = validate({"base": 15000, "pension_pct": 6, "occupation": "מפתחת תוכנה", "current_kind": "car",
                           "current_car": "EV3", "children": 2}, cfg, matcher)
    assert bad == {}
    assert clean["occupation"] == "מפתח/ת תוכנה"  # stored as in the sheet

    clean, bad = validate({"base": -5, "pension_pct": 60, "keren_pct": "abc", "occupation": "שף",
                           "current_kind": "family_car", "current_car_year": 1800}, cfg, matcher)
    assert clean == {}
    assert set(bad) == {"base", "pension_pct", "keren_pct", "occupation", "current_kind", "current_car_year"}
    assert 2 <= len(bad["occupation"]["suggestions"]) <= 3
    assert bad["base"]["range"] == cfg["ranges"]["base"]


def test_validate_refuses_group_and_unknown_fields(cfg, matcher):
    _, bad = validate({"group": "ג", "salary": 1}, cfg, matcher)
    assert set(bad) == {"group", "salary"}


def test_none_clears_a_field(cfg, matcher):
    clean, bad = validate({"bonus": None}, cfg, matcher)
    assert bad == {} and clean == {"bonus": None}


# --- the stores -------------------------------------------------------------------------------

@pytest.fixture(params=["memory", "postgres"])
def store(request):
    """(profiles, employee id): in Postgres the employee is added first (the profile's foreign key)."""
    emp = f"test-{uuid.uuid4().hex[:8]}"
    if request.param == "memory":
        yield InMemoryProfiles(), emp
        return
    if not DATABASE_URL:
        pytest.skip("no DATABASE_URL")
    from app.db import PostgresEmployees, PostgresProfiles, make_pool

    pool = make_pool(DATABASE_URL)
    employees = PostgresEmployees(pool, {emp: "עובד דמה"})
    employees.setup()
    profiles = PostgresProfiles(pool)
    profiles.setup()
    yield profiles, emp
    employees.delete([emp])  # the profile goes with it (on delete cascade)
    pool.close()


def test_an_employee_without_a_profile_has_no_fields(store):
    profiles, emp = store
    assert profiles.get(emp) == {}


def test_update_keeps_the_other_fields_and_the_latest_value_wins(store):
    profiles, emp = store
    profiles.update(emp, {"base": 15000, "occupation": "מפתח/ת תוכנה", "current_car": "EV3", "children": 2})
    profiles.update(emp, {"base": 16000.5, "pension_pct": 6})
    assert profiles.get(emp) == {"base": 16000.5, "occupation": "מפתח/ת תוכנה", "current_car": "EV3",
                                 "children": 2, "pension_pct": 6}


def test_none_clears(store):
    profiles, emp = store
    profiles.update(emp, {"base": 15000, "bonus": 500})
    profiles.update(emp, {"bonus": None})
    assert profiles.get(emp) == {"base": 15000}


def test_whole_numbers_come_back_as_ints(store):
    profiles, emp = store
    profiles.update(emp, {"children": 3, "current_car_year": 2025, "base": 15000})
    got = profiles.get(emp)
    assert isinstance(got["children"], int) and isinstance(got["current_car_year"], int)


# --- calculate with the profile (the code fills it in, not the model) ---------------------------

FULL = {"occupation": "מנהל/ת אזור מכירות", "base": 14200, "commission": 1000, "bonus": 0, "pension_pct": 6,
        "keren_pct": 2.5, "credit_points": 2.25, "current_kind": "car", "current_car": "TUCSON",
        "current_participation": 400}


@pytest.fixture
def advisor(data, cfg):
    profiles = InMemoryProfiles()
    return Advisor(data, InMemoryRepQueue(), cfg, profiles=profiles), profiles


def test_a_full_profile_is_enough_with_only_the_alternative(advisor, cfg):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert res["status"] == "ok"
    expected = adv.calculate({**FULL, "group": "ג", "alternative_kind": "car", "alternative_car": "EV3"})
    assert res["card"]["diff"] == expected["card"]["diff"]
    data = res["card"]["your_data"]
    assert data["base"] == {"value": 14200, "source": cfg["texts"]["sources"]["profile"]}
    assert data["group"]["value"] == "ג"  # from the occupation, in code
    assert data["group"]["source"] == cfg["texts"]["sources"]["occupation"]
    assert "profile_updated" not in res  # nothing new from the employee


def test_without_an_employee_nothing_comes_from_a_profile(advisor):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"})
    assert res["status"] == "missing"


def test_a_new_value_from_the_employee_wins_and_updates_the_profile(advisor, cfg):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"base": 15000, "alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert res["status"] == "ok"
    assert res["card"]["your_data"]["base"] == {"value": 15000, "source": cfg["texts"]["sources"]["employee"]}
    assert profiles.get("E01")["base"] == 15000
    assert res["profile_updated"] == ["base"]
    label = cfg["texts"]["profile"]["labels"]["base"]
    assert res["message_profile"] == cfg["texts"]["profile"]["updated"].format(fields=label)


def test_the_same_value_again_is_not_an_update(advisor):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"base": 14200, "alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert "profile_updated" not in res


def test_a_bad_value_is_not_kept(advisor):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"base": -3, "pension_pct": 7, "alternative_kind": "car", "alternative_car": "EV3"},
                        employee_id="E01")
    assert res["status"] == "invalid" and res["fields"] == ["base"]
    assert profiles.get("E01")["base"] == 14200
    assert profiles.get("E01")["pension_pct"] == 7  # the good one is kept
    assert res["profile_updated"] == ["pension_pct"]


def test_a_new_conversation_starts_with_the_profile(advisor):
    """The profile is per employee, not per conversation: another thread gets it as well."""
    adv, profiles = advisor
    adv.calculate({**FULL, "alternative_kind": "waiver"}, employee_id="E02", thread_id="t1")
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E02", thread_id="t2")
    assert res["status"] == "ok"


def test_three_or_more_missing_sends_the_profile_link_and_offers_the_payslip(advisor, cfg):
    adv, profiles = advisor
    profiles.update("E01", {"occupation": "מנהל/ת אזור מכירות", "current_kind": "car", "current_car": "TUCSON",
                            "current_participation": 400, "commission": 0, "bonus": 0})
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert res["status"] == "missing"
    assert set(res["fields"]) == {"base", "pension_pct", "keren_pct", "credit_points"}
    assert res["profile_link"] == cfg["profile"]["link"] == "/profile"
    assert res["message_to_employee"] == cfg["texts"]["profile"]["link"]
    assert "/profile" in res["message_to_employee"] and "תלוש" in res["message_to_employee"]


def test_one_or_two_missing_are_asked_as_usual(advisor):
    adv, profiles = advisor
    profiles.update("E01", {k: v for k, v in FULL.items() if k not in ("pension_pct", "keren_pct")})
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert res["status"] == "missing" and set(res["fields"]) == {"pension_pct", "keren_pct"}
    assert "profile_link" not in res and "message_to_employee" not in res


def test_the_alternative_is_not_counted_as_missing_from_the_profile(advisor):
    adv, profiles = advisor
    profiles.update("E01", {k: v for k, v in FULL.items() if k != "credit_points"})
    res = adv.calculate({}, employee_id="E01")
    assert set(res["fields"]) == {"credit_points", "alternative_kind"}
    assert "profile_link" not in res


def test_the_occupation_as_the_employee_wrote_it(advisor, data):
    adv, profiles = advisor
    res = adv.calculate({**FULL, "occupation": "מנהלת אזור המכירות", "alternative_kind": "waiver"},
                        employee_id="E01")
    assert res["status"] in ("ok", "not_eligible")
    assert profiles.get("E01")["occupation"] == "מנהל/ת אזור מכירות"


def test_an_unknown_occupation_is_not_guessed(advisor):
    adv, _ = advisor
    res = adv.calculate({**FULL, "occupation": "שף", "alternative_kind": "waiver"}, employee_id="E01")
    assert res["status"] == "invalid" and res["fields"] == ["occupation"]
    assert 2 <= len(res["options"]["occupation"]) <= 3


def test_a_group_the_employee_stated_against_the_occupation_is_still_a_contradiction(advisor):
    adv, profiles = advisor
    profiles.update("E01", FULL)
    res = adv.calculate({"group": "א", "alternative_kind": "car", "alternative_car": "EV3"}, employee_id="E01")
    assert res["status"] == "contradiction" and res["occupation_group"] == "ג"


def test_the_profile_is_below_the_payslip_of_this_conversation_only_when_older(advisor, cfg):
    """Latest wins: a payslip uploaded in the conversation already updated the profile (app/api),
    so the profile is the newer of the two and comes first."""
    from app.payslip import note
    adv, profiles = advisor
    profiles.update("E01", FULL)
    history = [note({"base": 9999}, "ok", cfg)]
    res = adv.calculate({"alternative_kind": "car", "alternative_car": "EV3"}, history=history, employee_id="E01")
    assert res["card"]["your_data"]["base"]["value"] == 14200
