"""The employee's participation, and an alternative car that is not in the catalog (no LLM; the graph ones run a
scripted fake model).

- Today's car: its participation comes from the employee (the profile, the payslip, the chat), never the catalog.
- A new car from the catalog: the participation is the catalog's default ("סכום ההשתתפות הרגיל לרכב הזה לפי
  קטלוג החברה"). No question to the employee, none to the rep.
- The rep, about the participation, only when the catalog has none, or the employee has a personal arrangement.
  Meanwhile the card shows today, and the alternative waits for the rep.
- An alternative outside the catalog: not_in_catalog, the catalog cars the employee may take (electric ones first
  when an electric car was asked for), no value of use, no net, no rep - even when the Tax Authority file has it.
- A name close to a catalog car: did_you_mean.
- Today's car is unchanged: outside the catalog it is looked up in the Tax Authority file, and a car that is not
  found there may still go to the rep."""
import copy
import json

import pytest
from langchain_core.messages import AIMessage

from app.agent.advisor import Advisor, load_agent_config
from app.agent.prompt import build_prompt
from app.agent.rep_queue import InMemoryRepQueue
from tests.agent.test_agent_advisor import has_number, src, tool_msg, val
from tests.agent.test_agent_graph import call, run, tool_results
from tests.conftest import BACKEND_DIR
from tests.test_profile import FULL


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


@pytest.fixture
def queue():
    return InMemoryRepQueue()


@pytest.fixture
def advisor(data, queue, cfg):
    return Advisor(data, queue, cfg)


def group_c(**alt):
    """A sales area manager (group ג), with a TUCSON today, asking about `alt`."""
    return dict(FULL, **alt)


def electric(data, name):
    return data.find_car(name)["drive"] == data.excel_values["electricDrive"]


# --- 1. a catalog car: the participation from the catalog, no rep ------------------------------

def test_group_c_electric_from_the_catalog_takes_the_catalogs_participation(advisor, data, cfg, queue):
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="EV3"))
    assert res["status"] == "ok"
    alt = res["card"]["alternative"]
    assert val(alt, "participation") == data.find_car("EV3")["defaultParticipation"]
    assert src(alt, "participation") == cfg["texts"]["sources"]["catalog"]
    assert res["participation_note"] == cfg["texts"]["catalogParticipation"]
    assert queue.pending("default") == []


def test_lookup_of_an_alternative_from_the_catalog_gives_its_participation(advisor, data, cfg):
    res = advisor.lookup_vehicle("EV3", alternative=True)
    assert res["status"] == "ok"
    assert res["car"]["participation"] == data.find_car("EV3")["defaultParticipation"]
    assert res["car"]["participation_note"] == cfg["texts"]["catalogParticipation"]


def test_the_catalog_car_is_checked_by_manufacturer_and_model_not_only_by_name(advisor, data):
    """"BYD SEAL U" holds the catalog's "SEAL", but the Tax Authority file gives it other codes: another car.
    "TANG" has ATTO 3's codes in that file, under another name: not ATTO 3 either. "BYD ATTO 3" is ATTO 3."""
    seal = data.find_car("SEAL")
    seal_u = [h for h in data.vehicles.search_name("BYD SEAL U") if h["name"] == "BYD SEAL U"]
    assert seal_u and all(h["modelCode"] != seal["modelCode"] for h in seal_u)
    for name in ("BYD SEAL U", "TANG"):
        assert advisor.calculate(group_c(alternative_kind="car", alternative_car=name))["status"] == "not_in_catalog"
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="BYD ATTO 3"))
    assert res["status"] == "ok" and res["card"]["alternative"]["label"].startswith("ATTO 3")


def test_todays_participation_never_comes_from_the_catalog(advisor):
    args = group_c(alternative_kind="car", alternative_car="EV3")
    del args["current_participation"]  # TUCSON is in the catalog, with a default: still asked of the employee
    res = advisor.calculate(args)
    assert res["status"] == "missing" and res["fields"] == ["current_participation"]


def test_the_family_track_keeps_half_the_gap(advisor, data):
    args = dict(FULL, occupation="מנהל/ת חטיבה", children=4, alternative_kind="family_car",
                alternative_car="SANTA FE")
    res = advisor.calculate(args)
    assert res["status"] == "ok"
    car, budget = data.find_car("SANTA FE"), data.rules["budgets"]["ד"]
    share = max(0, car["companyCost"] - budget) * data.rules["familyTrack"]["gapSplitEmployee"]
    assert val(res["card"]["alternative"], "family_share") == round(share)
    assert val(res["card"]["alternative"], "participation") == car["defaultParticipation"]


def test_through_the_graph_no_rep(data):
    out, queue = run(data, [call("calculate", group_c(alternative_kind="car", alternative_car="EV3")),
                            AIMessage(content="הנטו")])
    [res] = tool_results(out, "calculate")
    assert res["status"] == "ok"
    assert tool_results(out, "ask_rep") == [] and queue.pending("t") == []


# --- 2. outside the catalog: polite, the catalog's cars, no rep --------------------------------

def test_a_porsche_taycan_is_not_in_the_catalog(advisor, data, cfg):
    assert data.vehicles.search_name("TAYCAN")  # the Tax Authority file has it: still no value of use
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="PORSCHE TAYCAN"))
    assert res["status"] == "not_in_catalog"
    assert res["message_to_employee"] == cfg["texts"]["notInCatalog"]["message"]
    assert not has_number(res) and "valueOfUse" not in json.dumps(res)
    names = [o["name"] for o in res["options"]]
    order = data.rules["groupOrder"]
    for name in names:  # only cars the employee may take: group ג or lower, not the family track
        car = data.find_car(name)
        assert order.index(car["group"]) <= order.index("ג")
        assert car["id"] not in data.rules["familyTrack"]["cars"]
    may_take = [c["name"] for c in data.catalog.values() if c["group"] in order[:3]]
    assert sorted(names) == sorted(may_take)
    flags = [electric(data, n) for n in names]
    assert flags == sorted(flags, reverse=True)  # asked for an electric car: the electric ones first
    assert res["electric_first"] is True


def test_not_in_catalog_comes_before_the_salary_questions(advisor, cfg):
    """Nothing to calculate for it anyway: say so at once, not after asking for the payslip."""
    res = advisor.calculate({"alternative_kind": "car", "alternative_car": "PORSCHE TAYCAN"})
    assert res["status"] == "not_in_catalog"
    assert res["options"] == []  # no occupation yet: no group to choose by
    assert "occupation" in res["instruction"]


def test_not_in_catalog_in_check_eligibility_and_lookup(advisor):
    elig = advisor.check_eligibility({"occupation": FULL["occupation"], "alternative_kind": "car",
                                      "alternative_car": "PORSCHE TAYCAN"})
    assert elig["status"] == "not_in_catalog"
    assert advisor.lookup_vehicle("PORSCHE TAYCAN", alternative=True)["status"] == "not_in_catalog"


def test_atto2_as_an_alternative_is_not_in_the_catalog_and_has_no_rep(advisor, data):
    """The Tax Authority file has it (2025): still not calculated, and never sent to the rep."""
    assert data.vehicles.search_name("ATTO 2", registration_year=2025)
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="ATTO 2", alternative_car_year=2025))
    assert res["status"] == "not_in_catalog" and not has_number(res)


def test_an_unknown_alternative_is_not_in_the_catalog_even_twice(advisor):
    first = advisor.calculate(group_c(alternative_kind="car", alternative_car="ZORVEX 5"))
    second = advisor.calculate(group_c(alternative_kind="car", alternative_car="ZORVEX 5"),
                               history=[tool_msg("calculate", first)])
    assert first["status"] == second["status"] == "not_in_catalog"


def test_ask_rep_refuses_an_alternative_outside_the_catalog(advisor, queue):
    for fields, about in ((["carGroup", "companyCost", "participation"], None), (["car"], "alternative")):
        res = advisor.ask_rep(fields, "?", car="PORSCHE TAYCAN", about=about, thread_id="t")
        assert res["status"] == "not_in_catalog"
    assert queue.pending("t") == []


def test_porsche_through_the_graph(data, cfg):
    out, queue = run(data, [call("calculate", group_c(alternative_kind="car", alternative_car="PORSCHE TAYCAN")),
                            AIMessage(content=cfg["texts"]["notInCatalog"]["message"])])
    [res] = tool_results(out, "calculate")
    assert res["status"] == "not_in_catalog"
    assert tool_results(out, "ask_rep") == [] and queue.pending("t") == []


# --- 3. a personal arrangement, or a catalog car without a participation: the rep ---------------

def test_a_personal_arrangement_goes_to_the_rep_and_today_is_shown_meanwhile(advisor, data, queue, cfg):
    args = group_c(alternative_kind="car", alternative_car="EV3")
    sent = advisor.ask_rep(["participation"], "לעובד הסדר השתתפות אישי ל-EV3. מה הסכום?", car="EV3",
                           about="alternative", thread_id="t")
    assert sent["status"] == "sent" and sent["message_to_employee"] == cfg["texts"]["repSent"]

    waiting = advisor.calculate(args, thread_id="t")
    assert waiting["status"] == "waiting_rep" and waiting["fields"] == ["participation"]
    today, alt = waiting["card"]["today"], waiting["card"]["alternative"]
    assert isinstance(val(today, "net"), int)  # today is known
    assert val(alt, "participation") == val(alt, "net") == cfg["texts"]["pending"]  # no number invented

    queue.answer(queue.pending("t")[0]["id"], {"participation": 450})
    done = advisor.calculate(args, thread_id="t")
    assert done["status"] == "ok"
    assert val(done["card"]["alternative"], "participation") == 450
    assert src(done["card"]["alternative"], "participation") == cfg["texts"]["sources"]["rep"]
    assert "participation_note" not in done  # the rep's amount, not the catalog's


def test_a_catalog_car_without_a_participation_goes_to_the_rep_with_today_shown(data, queue, cfg):
    no_default = copy.copy(data)
    no_default.catalog = copy.deepcopy(data.catalog)
    no_default.catalog["CAR-11"]["defaultParticipation"] = None  # EV3
    no_default._catalog_by_name = {c["name"].strip().upper(): c for c in no_default.catalog.values()}
    res = Advisor(no_default, queue, cfg).calculate(group_c(alternative_kind="car", alternative_car="EV3"))
    assert res["status"] == "needs_rep" and res["fields"] == ["participation"]
    assert isinstance(val(res["card"]["today"], "net"), int)
    assert val(res["card"]["alternative"], "net") == cfg["texts"]["pending"]


def test_personal_arrangement_through_the_graph(data):
    args = group_c(alternative_kind="car", alternative_car="EV3")
    out, queue = run(data, [
        call("ask_rep", {"fields": ["participation"], "question": "הסדר השתתפות אישי ל-EV3?", "car": "EV3",
                         "about": "alternative"}, 0),
        call("calculate", args, 1),
        AIMessage(content="שלחתי שאלה לנציג התחבורה, והחלופה תתעדכן"),
    ])
    assert tool_results(out, "ask_rep")[0]["status"] == "sent"
    assert tool_results(out, "calculate")[0]["status"] == "waiting_rep"
    assert len(queue.pending("t")) == 1


# --- 4. a typo of a catalog car: did you mean ----------------------------------------------------

@pytest.mark.parametrize("name, meant", [("atto3", "ATTO 3"), ("ATOO 3", "ATTO 3"), ("TUSCON", "TUCSON"),
                                         ("KONA-EV", "KONA EV")])
def test_a_name_close_to_a_catalog_car_asks(advisor, name, meant):
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car=name))
    assert res["status"] == "did_you_mean"
    assert meant in res["suggestions"]
    assert not has_number(res)
    assert advisor.lookup_vehicle(name, alternative=True)["status"] == "did_you_mean"


def test_typo_through_the_graph(data):
    out, _ = run(data, [call("calculate", group_c(alternative_kind="car", alternative_car="atto3")),
                        AIMessage(content="התכוונת ל-ATTO 3?")])
    [res] = tool_results(out, "calculate")
    assert res["status"] == "did_you_mean" and res["suggestions"] == ["ATTO 3"]


# --- 5 and 6. today's car: as before ------------------------------------------------------------

def test_todays_car_outside_the_catalog_is_taken_from_the_tax_authority(advisor, data, cfg):
    args = group_c(current_car="ATTO 2", current_car_year=2025, alternative_kind="car", alternative_car="EV3")
    res = advisor.calculate(args)
    assert res["status"] == "ok"
    today = res["card"]["today"]
    rec = data.vehicles.search_name("ATTO 2", registration_year=2025)[0]
    assert val(today, "value_of_use") == rec["valueOfUse"]
    assert src(today, "value_of_use") == cfg["texts"]["sources"]["taxAuthority"]
    assert advisor.lookup_vehicle("ATTO 2", registration_year=2025)["status"] == "ok"  # today's: no refusal


def test_todays_car_not_found_may_still_go_to_the_rep(advisor, queue):
    first = advisor.lookup_vehicle("ZORVEX 5")
    second = advisor.lookup_vehicle("ZORVEX 5", history=[tool_msg("lookup_vehicle", first)])
    assert second["status"] == "needs_rep" and second["fields"] == ["car"]
    sent = advisor.ask_rep(["car"], "הרכב של העובד היום לא נמצא: ZORVEX 5", car="ZORVEX 5", about="current",
                           thread_id="t")
    assert sent["status"] == "sent" and len(queue.pending("t")) == 1


def test_todays_car_through_the_graph(data):
    out, queue = run(data, [
        call("lookup_vehicle", {"name": "ZORVEX 5"}, 0),
        call("lookup_vehicle", {"name": "ZORVEX 5"}, 1),
        call("ask_rep", {"fields": ["car"], "question": "הרכב של היום לא נמצא", "car": "ZORVEX 5",
                         "about": "current"}, 2),
        AIMessage(content="שלחתי שאלה לנציג התחבורה, והחלופה תתעדכן"),
    ])
    assert tool_results(out, "lookup_vehicle")[-1]["status"] == "needs_rep"
    assert tool_results(out, "ask_rep")[0]["status"] == "sent" and len(queue.pending("t")) == 1


# --- the prompt and the texts --------------------------------------------------------------------

def test_the_prompt_has_both_sections(data, cfg):
    prompt = build_prompt(data, cfg)
    assert "## השתתפות עובד ברכב" in prompt and "## רכב חלופה שלא נמצא בקטלוג" in prompt
    assert cfg["texts"]["catalogParticipation"] in prompt
    assert "not_in_catalog" in prompt and "did_you_mean" in prompt


def test_the_texts_are_in_agent_json(cfg):
    t = cfg["texts"]
    assert t["catalogParticipation"] == "סכום ההשתתפות הרגיל לרכב הזה לפי קטלוג החברה"
    assert "לא נמצא כרגע ברשימת רכבי החברה" in t["notInCatalog"]["message"]
