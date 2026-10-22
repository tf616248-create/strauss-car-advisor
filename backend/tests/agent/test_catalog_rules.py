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

def note(cfg, address, amount):
    """The sentence with the catalog's amount and the invitation to correct it, in the employee's form of address."""
    return cfg["texts"]["catalogParticipation"][address].format(amount=f"{amount:,}")


def test_group_c_electric_from_the_catalog_takes_the_catalogs_participation(advisor, data, cfg, queue):
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="EV3"))
    assert res["status"] == "ok"
    alt = res["card"]["alternative"]
    amount = data.find_car("EV3")["defaultParticipation"]
    assert val(alt, "participation") == amount
    assert src(alt, "participation") == cfg["texts"]["sources"]["catalog"]
    assert res["participation_note"] == note(cfg, "plural", amount)  # no form of address chosen: plural
    assert "awaiting_confirmation" not in res and "awaiting_confirmation" not in res["card"]
    assert queue.pending("default") == []


def test_lookup_of_an_alternative_from_the_catalog_gives_its_participation(advisor, data, cfg):
    res = advisor.lookup_vehicle("EV3", alternative=True)
    assert res["status"] == "ok"
    amount = data.find_car("EV3")["defaultParticipation"]
    assert res["car"]["participation"] == amount
    assert res["car"]["participation_note"] == note(cfg, "plural", amount)


@pytest.mark.parametrize("address, ask", [("male", "תגיד לי"), ("female", "תגידי לי"), ("plural", "תגידו לי")])
def test_the_catalog_note_says_where_the_amount_is_from_and_invites_a_correction(data, cfg, address, ask):
    """The sentence: from the catalog, the amount, and an invitation to correct it (to the rep)."""
    from app.profile import InMemoryProfiles

    profiles = InMemoryProfiles(cfg["settings"]["defaults"])
    profiles.update_settings("E01", {"address": address})
    advisor = Advisor(data, InMemoryRepQueue(), cfg, profiles=profiles)
    amount = data.find_car("EV3")["defaultParticipation"]
    calc = advisor.calculate(group_c(alternative_kind="car", alternative_car="EV3"), employee_id="E01")
    look = advisor.lookup_vehicle("EV3", alternative=True, employee_id="E01")
    for text in (calc["participation_note"], look["car"]["participation_note"]):
        assert text == note(cfg, address, amount)
        assert text.startswith("לפי קטלוג החברה, ההשתתפות ברכב הזה היא ") and f"{amount:,} ₪" in text
        assert ask in text and text.endswith("ואשאל את הנציג.")


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


# --- 3b. asking to confirm the catalog's amount: the rep, and meanwhile the catalog's calculation ----

def test_asking_to_confirm_the_amount_sends_the_rep_a_question_and_calculates_by_the_catalog(advisor, data, queue,
                                                                                              cfg):
    """"אפשר לוודא שזה הסכום שלי?" - no other arrangement claimed: the calculation by the catalog, awaiting
    the rep's confirmation (unlike a personal arrangement, where nothing is calculated meanwhile)."""
    args = group_c(alternative_kind="car", alternative_car="EV3")
    sent = advisor.ask_rep(["participation"], "העובד מבקש לאשר את סכום ההשתתפות ל-EV3", car="EV3",
                           about="alternative", confirm=True, thread_id="t")
    assert sent["status"] == "sent" and queue.pending("t")[0]["confirm"] is True

    res = advisor.calculate(args, thread_id="t")
    assert res["status"] == "ok" and res["awaiting_confirmation"] == ["participation"]
    alt = res["card"]["alternative"]
    amount = data.find_car("EV3")["defaultParticipation"]
    assert val(alt, "participation") == amount and src(alt, "participation") == cfg["texts"]["sources"]["catalog"]
    assert isinstance(val(alt, "net"), int)  # a real calculation, by the catalog's amount
    assert res["card"]["awaiting_confirmation"] == {"fields": ["participation"],
                                                    "label": cfg["texts"]["awaitingConfirmation"]["label"],
                                                    "note": cfg["texts"]["awaitingConfirmation"]["note"]}
    assert res["card"]["diff"]["net"] == advisor.calculate(args)["card"]["diff"]["net"]  # same as the catalog's
    assert "participation_note" not in res  # the question is already with the rep: no invitation to correct
    assert "instruction" in res


def test_the_reps_answer_overrides_the_catalogs_amount(advisor, data, queue, cfg):
    args = group_c(alternative_kind="car", alternative_car="EV3")
    advisor.ask_rep(["participation"], "לאשר את הסכום ל-EV3?", car="EV3", about="alternative", confirm=True,
                    thread_id="t")
    queue.answer(queue.pending("t")[0]["id"], {"participation": 450})
    done = advisor.calculate(args, thread_id="t")
    assert done["status"] == "ok"
    alt = done["card"]["alternative"]
    assert val(alt, "participation") == 450 and src(alt, "participation") == cfg["texts"]["sources"]["rep"]
    assert "awaiting_confirmation" not in done and "awaiting_confirmation" not in done["card"]
    assert "participation_note" not in done
    assert done["card"]["diff"]["net"] != advisor.calculate(args)["card"]["diff"]["net"]


def test_a_personal_arrangement_still_calculates_nothing_meanwhile(advisor, queue, cfg):
    """Without confirm (the employee says the amount is different): as before, no number."""
    advisor.ask_rep(["participation"], "הסדר אישי ל-EV3", car="EV3", about="alternative", thread_id="t")
    res = advisor.calculate(group_c(alternative_kind="car", alternative_car="EV3"), thread_id="t")
    assert res["status"] == "waiting_rep"
    assert val(res["card"]["alternative"], "net") == cfg["texts"]["pending"]


def test_confirm_is_only_for_a_car_to_move_to_from_the_catalog(advisor, queue):
    """Not for an alternative outside the catalog: refused as before."""
    res = advisor.ask_rep(["participation"], "לאשר?", car="PORSCHE TAYCAN", about="alternative", confirm=True,
                          thread_id="t")
    assert res["status"] == "not_in_catalog" and queue.pending("t") == []


def test_confirm_through_the_graph(data):
    args = group_c(alternative_kind="car", alternative_car="EV3")
    out, queue = run(data, [
        call("ask_rep", {"fields": ["participation"], "question": "העובד מבקש לאשר את סכום ההשתתפות ל-EV3",
                         "car": "EV3", "about": "alternative", "confirm": True}, 0),
        call("calculate", args, 1),
        AIMessage(content="שלחתי לנציג לאשר את הסכום. בינתיים החישוב לפי הקטלוג, ממתין לאישור."),
    ])
    assert tool_results(out, "ask_rep")[0]["status"] == "sent" and queue.pending("t")[0]["confirm"] is True
    [res] = tool_results(out, "calculate")
    assert res["status"] == "ok" and res["card"]["awaiting_confirmation"]["label"] == "ממתין לאישור"


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
    assert "participation_note" in prompt and "פעם אחת בשיחה לכל רכב" in prompt  # not in every message
    assert "confirm=true" in prompt and "awaiting_confirmation" in prompt
    assert "not_in_catalog" in prompt and "did_you_mean" in prompt


def test_the_texts_are_in_agent_json(cfg):
    t = cfg["texts"]
    assert t["catalogParticipation"] == {
        "male": "לפי קטלוג החברה, ההשתתפות ברכב הזה היא {amount} ₪. אם אצלך סוכם אחרת, תגיד לי ואשאל את הנציג.",
        "female": "לפי קטלוג החברה, ההשתתפות ברכב הזה היא {amount} ₪. אם אצלך סוכם אחרת, תגידי לי ואשאל את הנציג.",
        "plural": "לפי קטלוג החברה, ההשתתפות ברכב הזה היא {amount} ₪. אם אצלכם סוכם אחרת, תגידו לי ואשאל את הנציג.",
    }
    assert t["awaitingConfirmation"]["label"] == "ממתין לאישור"
    assert "לא נמצא כרגע ברשימת רכבי החברה" in t["notInCatalog"]["message"]
