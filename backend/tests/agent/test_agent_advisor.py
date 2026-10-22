"""The guards inside the agent's tools (no LLM involved).

Reference numbers come from the 'חישובים' sheet; other expectations are derived
from the data files or the engine - never typed here.
"""
import json
from dataclasses import replace

import pytest
from langchain_core.messages import ToolMessage

from app.agent.advisor import Advisor, load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.engine.net import compute_net
from app.engine.scenario import Choice, build_scenario
from tests.conftest import BACKEND_DIR
from tests.engine.test_reference_employees import employee_input

TOL = 1

# what each sample employee asks about (mirrors the 'השאלה' column)
ALTERNATIVES = {
    "E-001": {"alternative_kind": "car", "alternative_car": "ATTO 3"},
    "E-002": {"alternative_kind": "family_car", "alternative_car": "CARNIVAL"},
    "E-003": {"alternative_kind": "car", "alternative_car": "MG4"},
    "E-004": {"alternative_kind": "car", "alternative_car": "EV3"},
    "E-005": {"alternative_kind": "waiver"},
    "E-006": {"alternative_kind": "car", "alternative_car": "MODEL 3"},
}


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


@pytest.fixture
def queue():
    return InMemoryRepQueue()


@pytest.fixture
def advisor(data, queue, cfg):
    return Advisor(data, queue, cfg)


def employee_args(data, emp_id):
    """What the model would pass after talking with the employee."""
    row = data.employees[emp_id]
    args = {
        "occupation": row["occupation"],
        "group": row["group"],
        "base": row["base"],
        "commission": row["commission"],
        "bonus": row["bonus"],
        "pension_pct": row["pensionPct"],
        "keren_pct": row["kerenPct"],
        "credit_points": row["creditPoints"],
        "children": row["children"],
    }
    if data.find_car(row["currentCar"]) is None:  # "אין (אחזקה ...)"
        args["current_kind"] = "waiver"
    else:
        args.update(
            current_kind="car",
            current_car=row["currentCar"],
            current_participation=row["currentParticipation"],
        )
    args.update(ALTERNATIVES[emp_id])
    return args


def tool_msg(name, result):
    return ToolMessage(content=json.dumps(result, ensure_ascii=False), name=name, tool_call_id="x")


def val(side, key):
    return side["values"][key]["value"]


def src(side, key):
    return side["values"][key]["source"]


def has_number(result) -> bool:
    text = json.dumps(result, ensure_ascii=False)
    return "card" in result or '"net"' in text


# --- the 6 reference employees ------------------------------------------------


@pytest.mark.parametrize("emp_id", list(ALTERNATIVES))
def test_calculate_matches_reference_sheet(advisor, data, emp_id):
    res = advisor.calculate(employee_args(data, emp_id))
    assert res["status"] == "ok", res
    card, ref = res["card"], data.reference[emp_id]
    assert abs(val(card["today"], "net") - ref["netToday"]) <= TOL
    assert abs(val(card["alternative"], "net") - ref["netAlt"]) <= TOL
    assert abs(card["diff"]["net"] - ref["diff"]) <= TOL
    assert abs(val(card["today"], "tax") - ref["taxToday"]) <= TOL
    assert abs(val(card["alternative"], "tax") - ref["taxAlt"]) <= TOL
    assert abs(val(card["today"], "social") - ref["socialToday"]) <= TOL
    assert abs(val(card["alternative"], "social") - ref["socialAlt"]) <= TOL
    assert abs(val(card["alternative"], "electric_refund_gross") - ref["electricGross"]) <= TOL
    assert abs(val(card["alternative"], "family_share") - ref["familyShare"]) <= TOL


@pytest.mark.parametrize("emp_id", list(ALTERNATIVES))
def test_every_diff_is_ready_made_and_consistent(advisor, data, emp_id):
    """The model gets each component's difference, so it never has to subtract."""
    card = advisor.calculate(employee_args(data, emp_id))["card"]
    for key in ("value_of_use", "participation", "electric_refund_net", "maintenance",
                "family_share", "tax", "social", "net"):
        assert card["diff"][key] == val(card["alternative"], key) - val(card["today"], key), key
        assert isinstance(card["diff"][key], int)


def test_card_shows_your_data_with_employee_source(advisor, data, cfg):
    args = employee_args(data, "E-001")
    card = advisor.calculate(args)["card"]
    employee = cfg["texts"]["sources"]["employee"]
    for field in ("base", "commission", "bonus", "pension_pct", "keren_pct", "credit_points"):
        assert card["your_data"][field] == {"value": args[field], "source": employee}
    assert card["your_data"]["current_participation"]["value"] == args["current_participation"]


def test_card_sources(advisor, data, cfg):
    s = cfg["texts"]["sources"]
    card = advisor.calculate(employee_args(data, "E-001"))["card"]
    assert src(card["alternative"], "value_of_use") == s["catalog"]
    assert src(card["alternative"], "participation") == s["catalog"]
    assert src(card["today"], "participation") == s["employee"]
    assert src(card["alternative"], "electric_refund_net") == s["rules"]


def test_card_has_two_line_explanation(advisor, data):
    card = advisor.calculate(employee_args(data, "E-001"))["card"]
    assert len(card["explanation"]) == 2
    assert str(abs(card["diff"]["net"])) in card["explanation"][1].replace(",", "")


def test_electric_refund_net_is_exactly_the_rule(advisor, data):
    card = advisor.calculate(employee_args(data, "E-001"))["card"]
    assert val(card["alternative"], "electric_refund_net") == data.rules["electric"]["netBonus"]


# --- missing / invalid employee data: ask, never guess ------------------------


def test_missing_field_returns_missing_and_no_numbers(advisor, data):
    args = employee_args(data, "E-001")
    del args["base"]
    res = advisor.calculate(args)
    assert res["status"] == "missing"
    assert "base" in res["fields"]
    assert not has_number(res)


def test_children_required_only_for_family_track(advisor, data):
    args = employee_args(data, "E-001")
    del args["children"]
    assert advisor.calculate(args)["status"] == "ok"
    args = employee_args(data, "E-002")
    del args["children"]
    res = advisor.calculate(args)
    assert res["status"] == "missing" and res["fields"] == ["children"]


def test_invalid_value_keeps_asking_the_employee(advisor, data):
    """The rep cannot know an anonymous employee's salary data: it never goes to the rep."""
    args = dict(employee_args(data, "E-001"), pension_pct=60)
    first = advisor.calculate(args)
    assert first["status"] == "invalid" and "pension_pct" in first["fields"]
    assert not has_number(first)
    history = [tool_msg("calculate", first)]
    for _ in range(3):
        again = advisor.calculate(args, history=history)
        assert again["status"] == "invalid" and "pension_pct" in again["fields"]
        history.append(tool_msg("calculate", again))


def test_second_failed_attempt_says_where_to_find_the_value(advisor, data):
    args = dict(employee_args(data, "E-001"), pension_pct=60)
    first = advisor.calculate(args)
    assert "תלוש" not in first["instruction"]
    second = advisor.calculate(args, history=[tool_msg("calculate", first)])
    assert "תלוש" in second["instruction"]


def test_missing_value_keeps_asking_and_then_says_where_to_find_it(advisor, data):
    args = employee_args(data, "E-001")
    del args["base"]
    first = advisor.calculate(args)
    assert "תלוש" not in first["instruction"]
    second = advisor.calculate(args, history=[tool_msg("calculate", first)])
    assert second["status"] == "missing" and "base" in second["fields"]
    assert "תלוש" in second["instruction"]


def test_unknown_occupation_offers_2_or_3_close_ones(advisor, data):
    """Not the whole list any more: the closest occupations from the sheet (app/profile.py), to ask about."""
    args = dict(employee_args(data, "E-001"), occupation="אסטרונאוט")
    res = advisor.calculate(args)
    assert res["status"] == "invalid" and "occupation" in res["fields"]
    assert 2 <= len(res["options"]["occupation"]) <= 3
    assert set(res["options"]["occupation"]) <= set(data.occupations)


def test_no_participation_argument_for_the_alternative(advisor):
    """'What if I pay 200?' - the tool has no way to take it."""
    assert "alternative_participation" not in Advisor.CALCULATE_FIELDS


# --- group contradiction ------------------------------------------------------


def test_group_contradiction_is_reported(advisor, data):
    args = dict(employee_args(data, "E-001"), group="ד")  # product manager is group ג
    res = advisor.calculate(args)
    assert res["status"] == "contradiction"
    assert res["occupation_group"] == data.occupations[args["occupation"]]["group"]
    assert not has_number(res)


def test_group_contradiction_resolved_by_rep(advisor, data, queue):
    args = dict(employee_args(data, "E-001"), group="ד")
    advisor.ask_rep(["group"], "העובדת מתעקשת שהיא בקבוצה ד", thread_id="t")
    assert advisor.calculate(args, thread_id="t")["status"] == "waiting_rep"
    queue.answer(queue.pending("t")[0]["id"], {"group": "ג"})
    assert advisor.calculate(args, thread_id="t")["status"] == "ok"


# --- eligibility --------------------------------------------------------------


def test_check_eligibility_not_eligible(advisor, data):
    args = dict(employee_args(data, "E-003"), alternative_car="MODEL 3")
    res = advisor.check_eligibility(args)
    assert res["eligible"] is False and res["reason_code"] == "group_too_high"


def test_calculate_not_eligible_gives_reason_not_numbers(advisor, data):
    args = dict(employee_args(data, "E-002"), alternative_kind="waiver")
    del args["alternative_car"]
    res = advisor.calculate(args)
    assert res["status"] == "not_eligible" and res["reason_code"] == "waiver_not_allowed"
    assert not has_number(res)


# --- vehicle lookup -----------------------------------------------------------


def test_lookup_catalog_car(advisor, data, cfg):
    res = advisor.lookup_vehicle("BYD ATTO 3")
    assert res["status"] == "ok"
    car = data.find_car("ATTO 3")
    assert res["car"]["inCatalog"] is True
    assert res["car"]["valueOfUse"] == car["valueOfUse"]
    assert res["car"]["source"] == cfg["texts"]["sources"]["catalog"]


def test_lookup_outside_catalog_uses_tax_authority(advisor, data, cfg):
    res = advisor.lookup_vehicle("ATTO 2", registration_year=2025)
    assert res["status"] == "ok"
    assert res["car"]["inCatalog"] is False
    assert res["car"]["source"] == cfg["texts"]["sources"]["taxAuthority"]
    expected = data.vehicles.search_name("ATTO 2", registration_year=2025)
    assert res["car"]["valueOfUse"] == expected[0]["valueOfUse"]  # today's car: as before
    assert "companyFields" not in res  # as an alternative it is not in the catalog (test_catalog_rules.py)


def test_lookup_ambiguous_returns_candidates(advisor):
    res = advisor.lookup_vehicle("MODEL Y", registration_year=2025)
    assert res["status"] == "ambiguous"
    assert len({c["modelCode"] for c in res["candidates"]}) > 1


def test_lookup_not_found_twice_goes_to_rep(advisor):
    first = advisor.lookup_vehicle("ZZZ NO SUCH CAR")
    assert first["status"] == "not_found"
    second = advisor.lookup_vehicle("ZZZ NO SUCH CAR 2", history=[tool_msg("lookup_vehicle", first)])
    assert second["status"] == "needs_rep" and second["fields"] == ["car"]


def test_lookup_failures_reset_after_success(advisor):
    fail = advisor.lookup_vehicle("ZZZ NO SUCH CAR")
    ok = advisor.lookup_vehicle("MG4")
    res = advisor.lookup_vehicle("ZZZ", history=[tool_msg("lookup_vehicle", fail), tool_msg("lookup_vehicle", ok)])
    assert res["status"] == "not_found"


# --- Rachel (E-003): ATTO 2 is not in the catalog; her personal arrangement for MG4 is the rep's case --------


def rachel_atto2(data):
    return dict(employee_args(data, "E-003"), alternative_car="ATTO 2", alternative_car_year=2025)


def test_atto2_is_not_in_the_catalog_and_not_for_the_rep(advisor, data, queue):
    """The Tax Authority file has it: still no value of use, no net, and no question to the rep."""
    res = advisor.calculate(rachel_atto2(data))
    assert res["status"] == "not_in_catalog"
    assert not has_number(res)
    assert advisor.ask_rep(["carGroup", "companyCost", "participation"], "BYD Atto 2?", car="ATTO 2",
                           registration_year=2025, thread_id="t")["status"] == "not_in_catalog"
    assert queue.pending("t") == []


def personal_arrangement(advisor, car="MG4", thread="t"):
    return advisor.ask_rep(["participation"], f"לעובדת הסדר השתתפות אישי ל-{car}. מה הסכום?", car=car,
                           about="alternative", thread_id=thread)


def test_ask_rep_message_and_no_duplicates(advisor, queue, cfg):
    first = personal_arrangement(advisor)
    assert first["status"] == "sent"
    assert first["message_to_employee"] == cfg["texts"]["repSent"]
    assert "פנה לנציג" not in json.dumps(first, ensure_ascii=False)
    personal_arrangement(advisor)
    assert len(queue.pending("t")) == 1


def test_personal_arrangement_waiting_then_answered(advisor, data, queue, cfg):
    args = employee_args(data, "E-003")  # MG4
    personal_arrangement(advisor)

    waiting = advisor.calculate(args, thread_id="t")
    assert waiting["status"] == "waiting_rep"
    alt = waiting["card"]["alternative"]
    pending = cfg["texts"]["pending"]
    for key in ("participation", "net"):
        assert val(alt, key) == pending
    assert val(alt, "value_of_use") == data.find_car("MG4")["valueOfUse"]  # known from the catalog
    assert abs(val(waiting["card"]["today"], "net") - data.reference["E-003"]["netToday"]) <= TOL

    queue.answer(queue.pending("t")[0]["id"], {"participation": 250})
    done = advisor.calculate(args, thread_id="t")
    assert done["status"] == "ok"
    alt = done["card"]["alternative"]
    s = cfg["texts"]["sources"]
    assert src(alt, "participation") == s["rep"]
    assert src(alt, "value_of_use") == s["catalog"]

    # same numbers as the engine with the same inputs
    emp = employee_input(data.employees["E-003"])
    scen = build_scenario(emp, Choice.car("MG4", participation=250), data).scenario
    assert val(alt, "net") == round(compute_net(emp, scen, data.rules).net)


def test_a_rep_answer_does_not_make_a_car_above_the_group_eligible(advisor, data, queue):
    personal_arrangement(advisor, car="MODEL 3")  # group ד; Rachel is in group ב
    queue.answer(queue.pending("t")[0]["id"], {"participation": 250})
    res = advisor.calculate(dict(employee_args(data, "E-003"), alternative_car="MODEL 3"), thread_id="t")
    assert res["status"] == "not_eligible" and res["reason_code"] == "group_too_high"


def test_rep_answers_are_per_conversation(advisor, data, queue, cfg):
    personal_arrangement(advisor, thread="t1")
    queue.answer(queue.pending("t1")[0]["id"], {"participation": 250})
    other = advisor.calculate(employee_args(data, "E-003"), thread_id="t2")
    assert other["status"] == "ok"
    assert src(other["card"]["alternative"], "participation") == cfg["texts"]["sources"]["catalog"]


def test_ask_rep_refuses_employee_salary_fields(advisor):
    """The rep cannot know an anonymous employee's data; the guard is in the tool, not only the prompt."""
    res = advisor.ask_rep(["base", "pension_pct"], "מה השכר?", thread_id="t-guard")
    assert res["status"] == "not_for_rep"
    assert res["fields"] == ["base", "pension_pct"]
    assert "תלוש" in res["instruction"]
    assert advisor.queue.pending("t-guard") == []


def test_ask_rep_still_takes_company_fields_car_and_group(advisor):
    for fields in (["carGroup", "companyCost", "participation"], ["car"], ["group"]):
        assert advisor.ask_rep(fields, "?", thread_id="t-ok")["status"] == "sent", fields


# --- payslip: values read in code fill what the model did not pass -------------


def test_payslip_values_fill_missing_fields(advisor, data, cfg):
    from app.payslip import note

    args = employee_args(data, "E-001")
    from_payslip = {f: args.pop(f) for f in ("base", "pension_pct", "credit_points")}
    res = advisor.calculate(args, history=[note(from_payslip, "ok", cfg)])
    assert res["status"] == "ok"
    payslip_src = cfg["texts"]["sources"]["payslip"]
    for field, value in from_payslip.items():
        assert res["card"]["your_data"][field] == {"value": value, "source": payslip_src}
    # same numbers as when the employee typed them
    assert res["card"] == {**advisor.calculate(employee_args(data, "E-001"))["card"], "your_data": res["card"]["your_data"]}


def test_what_the_employee_says_beats_the_payslip(advisor, data, cfg):
    """A correction after the upload ("my base is actually ...") is passed by the model and wins."""
    from app.payslip import note

    args = employee_args(data, "E-001")
    res = advisor.calculate(args, history=[note({"base": args["base"] + 1000}, "ok", cfg)])
    assert res["card"]["your_data"]["base"] == {"value": args["base"], "source": cfg["texts"]["sources"]["employee"]}


def test_a_field_not_on_the_payslip_is_still_asked(advisor, data, cfg):
    from app.payslip import note

    args = employee_args(data, "E-001")
    del args["credit_points"], args["base"]
    res = advisor.calculate(args, history=[note({"base": 12000}, "ok", cfg)])
    assert res["status"] == "missing" and res["fields"] == ["credit_points"]
