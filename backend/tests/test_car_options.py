"""car_specs and rank_options: what is known about a catalog car, and the cars an employee is
eligible for, filtered and sorted in code, with the net from the same engine as calculate.
Specs come from the snapshot (cache/specs-snapshot.json): no network here."""
import copy

import pytest

from app.agent.advisor import Advisor, load_agent_config
from app.agent.car_options import CarOptions
from app.agent.rep_queue import InMemoryRepQueue
from app.data.specs_store import SpecsStore, load_specs_config, snapshot_store
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args

ELECTRIC = {"BYD DOLPHIN", "MG4", "KONA EV", "ATTO 3", "EV3", "MODEL 3", "SEAL"}


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


@pytest.fixture(scope="module")
def store():
    return snapshot_store(BACKEND_DIR)


def make(data, cfg, store, specs_cfg=None):
    advisor = Advisor(data, InMemoryRepQueue(), cfg)
    return CarOptions(advisor, store, specs_cfg or load_specs_config(BACKEND_DIR)), advisor


def employee(data, emp_id):
    """Employee and today's car, without the alternative (rank_options picks the cars)."""
    return {k: v for k, v in employee_args(data, emp_id).items() if not k.startswith("alternative")}


# --- car_specs ---------------------------------------------------------------------


def test_every_spec_has_a_source_and_a_date(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.car_specs("BYD DOLPHIN")
    assert res["status"] == "ok"
    assert res["specs"]
    for field, item in res["specs"].items():
        assert item["source"], field
        assert item["fetched_at"], field
        assert item["year"], field
        assert "value" in item or "min" in item, field


def test_no_value_without_data(data, cfg, store):
    """gova (height) is empty in the source: not shown. The commercial name is not a spec."""
    opts, _ = make(data, cfg, store)
    specs = opts.car_specs("BYD DOLPHIN")["specs"]
    assert "gova" not in specs
    assert "kinuy_mishari" not in specs
    assert all(item.get("value") is not None or item.get("min") is not None for item in specs.values())


def test_min_equal_to_max_is_one_value(data, cfg, store):
    opts, _ = make(data, cfg, store)
    hp = opts.car_specs("BYD DOLPHIN")["specs"]["koah_sus"]
    assert hp["value"] == 204
    assert "min" not in hp and "max" not in hp
    assert hp["label"] == "כוח סוס"


def test_a_spec_that_varies_by_trim_is_a_range(data, cfg):
    fake = {"mot": lambda: {"source": "משרד התחבורה", "cars": {"CAR-03": {"fields": {
        "koah_sus": {"min": 150, "max": 204, "variesByTrim": True}}, "fuelConsumption": {"status": "not_applicable"}}}}}
    store = SpecsStore(fake, BACKEND_DIR / "no-such-snapshot.json", 24)
    store.load_all()
    opts, _ = make(data, cfg, store)
    hp = opts.car_specs("BYD DOLPHIN")["specs"]["koah_sus"]
    assert (hp["min"], hp["max"], hp["varies_by_trim"]) == (150, 204, True)
    assert "value" not in hp


def test_eea_consumption_is_marked_provisional(data, cfg, store):
    opts, _ = make(data, cfg, store)
    item = opts.car_specs("BYD DOLPHIN")["specs"]["electric_consumption"]
    assert item["value"] == 159
    assert item["unit"] == "Wh/km"
    assert item["provisional"] is True
    assert item["year"] == 2025
    assert "EEA" in item["source"]


def test_fuel_consumption_is_approximate(data, cfg, store):
    opts, _ = make(data, cfg, store)
    item = opts.car_specs("COROLLA")["specs"]["fuel_consumption"]
    assert item["value"] == 5.75
    assert item["approximate"] is True


def test_the_importer_link_comes_with_the_specs(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.car_specs("BYD DOLPHIN")["importer_url"].startswith("https://")


def test_a_car_without_official_specs_says_so_with_the_link(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.car_specs("SANTA FE")
    assert res["status"] == "no_official_data"
    assert res["message"] == "אין נתון רשמי"
    assert res["importer_url"].startswith("https://")
    assert "specs" not in res


def test_a_car_outside_the_catalog_has_no_specs(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.car_specs("ATTO 2")["status"] == "not_in_catalog"


# --- rank_options ------------------------------------------------------------------
# rank_options returns (result, card): the result goes to the model (short), the card to the
# screen (full specs) through the tool's artifact - the model never reads it.

MODEL_BUDGET = 2000  # characters of the result the model reads


def calculated(advisor, args):
    """Every catalog car the employee may take, with calculate's net - computed independently."""
    out = {}
    for car in advisor.data.catalog.values():
        kind = "family_car" if car["id"] in advisor.data.rules["familyTrack"]["cars"] else "car"
        res = advisor.calculate({**args, "alternative_kind": kind, "alternative_car": car["name"]})
        if res["status"] == "ok":
            out[car["name"]] = res["card"]
    return out


def all_ranked(data, cfg, store):
    """The whole order, not only the top 3."""
    specs_cfg = copy.deepcopy(load_specs_config(BACKEND_DIR))
    specs_cfg["agent"]["top"] = 20
    return make(data, cfg, store, specs_cfg)[0]


def test_ranks_by_net_only_eligible_cars_with_the_same_net_as_calculate(data, cfg, store):
    opts, advisor = make(data, cfg, store)
    args = employee(data, "E-001")  # group ג, 2 children
    res, card = opts.rank_options(args, {}, "net")
    assert res["status"] == "ok"
    expected = calculated(advisor, args)
    best = sorted(expected, key=lambda n: -expected[n]["alternative"]["values"]["net"]["value"])[:3]
    assert [o["car"] for o in res["options"]] == best
    for o in res["options"]:
        assert o["net"] == expected[o["car"]]["alternative"]["values"]["net"]["value"]
        assert o["diff"] == {k: v for k, v in expected[o["car"]]["diff"].items() if v}  # what changed
    assert all(data.find_car(o["car"])["group"] in ("א", "ב", "ג") for o in res["options"])


def test_net_is_the_default_sort(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-001"), {}, None)[0]["sort_by"] == "net"


def test_sort_by_safety_highest_first(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {}, "safety")  # group ד: most of the catalog
    values = [o["sort_value"]["value"] for o in res["options"]]
    assert values == sorted(values, reverse=True)
    assert res["options"][0]["car"] == "KONA EV"  # 10.5, the highest in the snapshot
    assert res["direction"] == "higher_is_safer"


# --- pollution: electric cars are "no tailpipe emissions", not a made-up group ---------


def test_sort_by_pollution_electric_first_then_plug_in(data, cfg, store):
    opts = all_ranked(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {}, "pollution")
    order = [o["car"] for o in res["options"]]
    electric = [i for i, c in enumerate(order) if c in ELECTRIC]
    assert len(electric) == len(ELECTRIC)  # none left out for missing data
    assert max(electric) < order.index("SPORTAGE HEV")
    for o in res["options"]:
        if o["car"] in ELECTRIC:
            assert o["sort_value"] == {"category": "zero_tailpipe", "label": "ללא פליטות מהמפלט",
                                       "source": o["sort_value"]["source"]}
            assert "value" not in o["sort_value"]  # no invented pollution group
    groups = [o["sort_value"]["value"] for o in res["options"] if o["car"] not in ELECTRIC]
    assert groups == sorted(groups)
    assert not ELECTRIC & {m["car"] for m in res["excluded_missing_data"]}


def test_max_pollution_group_lets_electric_cars_through(data, cfg, store):
    opts = all_ranked(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {"max_pollution_group": 3}, "net")
    cars = {o["car"] for o in res["options"]}
    assert ELECTRIC <= cars
    assert "SPORTAGE HEV" in cars  # group 2
    assert "TUCSON" not in cars  # group 14


def test_the_direction_comes_from_the_config(data, cfg, store):
    specs_cfg = copy.deepcopy(load_specs_config(BACKEND_DIR))
    specs_cfg["indices"]["nikud_betihut"]["direction"] = "lower_is_safer"
    opts, _ = make(data, cfg, store, specs_cfg)
    values = [o["sort_value"]["value"] for o in opts.rank_options(employee(data, "E-006"), {}, "safety")[0]["options"]]
    assert values == sorted(values)


# --- ties ----------------------------------------------------------------------------


def flat_safety_store():
    """Every car the same safety score."""
    snap = snapshot_store(BACKEND_DIR)
    flat = copy.deepcopy(snap._data)
    for car in flat["mot"]["cars"].values():
        car["fields"]["nikud_betihut"] = {"min": 5, "max": 5, "variesByTrim": False}
    store = SpecsStore({name: (lambda e=e: e) for name, e in flat.items()}, BACKEND_DIR / "none.json", 24)
    store.load_all()
    return store


def test_a_tie_is_broken_by_net_and_flagged(data, cfg):
    opts, _ = make(data, cfg, flat_safety_store())
    args = employee(data, "E-006")
    res, card = opts.rank_options(args, {}, "safety")
    nets = [o["net"] for o in res["options"]]
    assert nets == sorted(nets, reverse=True)
    assert [o["car"] for o in res["options"]] == [o["car"] for o in opts.rank_options(args, {}, "net")[0]["options"]]
    assert all(o["tie_broken_by_net"] is True for o in res["options"])
    assert all(o["tie_broken_by_net"] is True for o in card["options"])


def test_no_tie_no_flag(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {}, "safety")  # 10.5, 9.5, 9.0
    assert [o["tie_broken_by_net"] for o in res["options"]] == [False, False, False]
    by_net, _ = opts.rank_options(employee(data, "E-006"), {}, "net")
    assert not any(o["tie_broken_by_net"] for o in by_net["options"])


def test_the_prompt_says_how_to_tell_a_tie():
    from app.agent.prompt import TEMPLATE

    assert ("אם tie_broken_by_net, אומרים זאת לעובד, למשל: 'לשלושתם אותו ניקוד בטיחות, "
            "אז סידרתי ביניהם לפי מה שמשאיר לך יותר כסף בנטו'.") in TEMPLATE


# --- what the model reads, and what the screen gets ------------------------------------


SCENARIOS = [
    ("E-001", {}, "net"),
    ("E-006", {}, "pollution"),
    ("E-006", {}, "safety"),
    ("E-006", {"drive": ["electric"]}, "consumption"),
    ("E-002", {"min_seats": 7}, "net"),
    ("E-006", {"body_type": ["סדאן", "פנאי-שטח"], "adaptive_cruise": True, "reverse_camera": True,
               "min_safety_score": 2, "min_horsepower": 100, "max_participation": 500}, "power"),
]


@pytest.mark.parametrize("emp, filters, sort_by", SCENARIOS)
def test_the_model_reads_less_than_2000_characters(data, cfg, store, emp, filters, sort_by):
    import json

    opts, _ = make(data, cfg, store)
    res, card = opts.rank_options(employee(data, emp), filters, sort_by)
    assert len(json.dumps(res, ensure_ascii=False)) < MODEL_BUDGET
    assert "specs" not in json.dumps(res)


def test_the_model_gets_only_the_fields_it_filtered_and_sorted_by_with_a_source(data, cfg, store):
    """fields: {source: {label: value}} - each source written once. The sort field is in sort_value."""
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"),
                               {"min_seats": 5, "reverse_camera": True, "min_safety_score": 1,
                                "max_participation": 500}, "safety")
    for o in res["options"]:
        assert set(o) == {"rank", "car", "net", "diff", "sort_value", "fields", "tie_broken_by_net"}
        car = data.find_car(o["car"])
        assert o["fields"] == {f"משרד התחבורה, {car['registrationYear']}": {"מושבים": 5, "מצלמת רוורס": True},
                               "קטלוג": {"השתתפות חודשית": car["defaultParticipation"]}}
        assert o["sort_value"]["label"] == "ניקוד בטיחות"
        assert o["sort_value"]["source"].startswith("משרד התחבורה")
        assert all(v != 0 for v in o["diff"].values())  # only what changed
        assert "net" in o["diff"] or o["net"] is not None


def test_the_card_has_the_full_specs(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, card = opts.rank_options(employee(data, "E-006"), {"min_seats": 5}, "safety")
    assert card["type"] == "ranking"
    assert [o["car"] for o in card["options"]] == [o["car"] for o in res["options"]]
    first = card["options"][0]
    assert first["specs"] == opts.car_specs(first["car"])["specs"]  # the same full specs as car_specs
    assert first["importer_url"].startswith("https://")
    assert card["sort_by"] == "safety" and card["applied_filters"] == {"min_seats": 5}
    assert card["sort_label"] == "ניקוד בטיחות"
    _, by_pollution = opts.rank_options(employee(data, "E-006"), {}, "pollution")
    assert by_pollution["sort_label"] == "קבוצת זיהום"  # the field, not the first car's category


def test_no_card_when_nothing_is_ranked(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, card = opts.rank_options(employee(data, "E-001"), {"min_seats": 9}, "net")
    assert res["status"] == "no_match" and res["options"] == []
    assert card is None


# --- filters -------------------------------------------------------------------------


def test_filters_drive_and_participation(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-001"), {"drive": ["electric"], "max_participation": 250}, "net")
    assert res["options"]
    for o in res["options"]:
        car = data.find_car(o["car"])
        assert car["name"] in ELECTRIC
        assert car["defaultParticipation"] <= 250
    assert res["applied_filters"] == {"drive": ["electric"], "max_participation": 250}


def test_min_seats_and_a_car_without_specs_is_reported(data, cfg, store):
    """David (E-002) has 5 children: the family track. SANTA FE has no official specs."""
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-002"), {"min_seats": 7}, "net")
    assert [o["car"] for o in res["options"]] == ["CARNIVAL"]
    assert {"car": "SANTA FE", "field": "mispar_moshavim", "label": "מושבים"} in res["excluded_missing_data"]


def test_flags_and_body_type(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, card = opts.rank_options(employee(data, "E-006"),
                                  {"body_type": ["סדאן"], "adaptive_cruise": True, "reverse_camera": True}, "net")
    assert card["options"]
    for o in card["options"]:
        specs = o["specs"]
        assert specs["merkav"]["value"] == "סדאן"
        assert specs["bakarat_shyut_adaptivit_ind"]["value"] is True
        assert specs["matzlemat_reverse_ind"]["value"] is True


def test_min_safety_and_power(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {"min_safety_score": 8, "min_horsepower": 250}, "net")
    assert res["options"]
    for o in opts.rank_options(employee(data, "E-006"), {"min_safety_score": 8, "min_horsepower": 250},
                               "net")[1]["options"]:
        assert o["specs"]["nikud_betihut"]["value"] >= 8
        assert o["specs"]["koah_sus"]["value"] >= 250
    assert "MODEL 3" in {m["car"] for m in res["excluded_missing_data"]}  # horsepower 0 = no data


def test_consumption_cannot_mix_electricity_and_fuel(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-006"), {}, "consumption")[0]["status"] == "mixed_units"
    res, _ = opts.rank_options(employee(data, "E-006"), {"drive": ["electric"]}, "consumption")
    values = [o["sort_value"]["value"] for o in res["options"]]
    assert values == sorted(values)
    assert res["options"][0]["sort_value"]["unit"] == "Wh/km"


def test_a_car_that_fails_a_filter_is_not_reported_as_missing_data(data, cfg, store):
    """MAZDA 3 has no fuel consumption, but it is petrol: an electric-only list just doesn't show it."""
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-006"), {"drive": ["electric"]}, "consumption")
    assert "MAZDA 3" not in {m["car"] for m in res["excluded_missing_data"]}


def test_a_car_without_participation_needs_the_rep_and_is_not_ranked(data, cfg, store, monkeypatch):
    monkeypatch.setitem(data.catalog["CAR-10"], "defaultParticipation", None)  # ATTO 3
    opts, _ = make(data, cfg, store)
    res, _ = opts.rank_options(employee(data, "E-001"), {"drive": ["electric"]}, "net")
    assert {"car": "ATTO 3", "fields": ["participation"]} in res["needs_rep"]
    assert "ATTO 3" not in [o["car"] for o in res["options"]]


def test_missing_employee_data_is_asked_first(data, cfg, store):
    opts, _ = make(data, cfg, store)
    args = employee(data, "E-001")
    del args["base"]
    res, card = opts.rank_options(args, {}, "net")
    assert res["status"] == "missing"
    assert "base" in res["fields"]
    assert card is None


def test_an_unknown_sort_or_filter_is_invalid(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-001"), {}, "beauty")[0]["status"] == "invalid"
    assert opts.rank_options(employee(data, "E-001"), {"trunk": 400}, "net")[0]["status"] == "invalid"


# --- the card reaches the screen like the comparison card ------------------------------


def test_the_ranking_card_goes_to_the_screen_and_not_to_the_rep():
    import json

    from langchain_core.messages import ToolMessage

    from app.api.common import cards_of, comparison_cards

    calc = ToolMessage(content=json.dumps({"status": "ok", "card": {"diff": {"net": 1}}}), tool_call_id="1",
                       name="calculate")
    rank = ToolMessage(content=json.dumps({"status": "ok", "options": []}), tool_call_id="2", name="rank_options",
                       artifact={"type": "ranking", "options": [{"car": "KONA EV", "specs": {"koah_sus": {}}}]})
    cards = cards_of([calc, rank])
    assert cards[1] == {"status": "ok", "kind": "ranking",
                        "card": {"type": "ranking", "options": [{"car": "KONA EV", "specs": {"koah_sus": {}}}]}}
    assert cards[0]["kind"] == "comparison"
    assert comparison_cards(cards) == [cards[0]]  # the rep sees the employee's comparison only


def test_the_ranking_card_reaches_the_screen_over_sse(data, cfg):
    from langchain_core.messages import AIMessage

    from tests.test_agent_graph import call
    from tests.test_api import chat, make as make_client

    args = employee(data, "E-006")
    client, _, _ = make_client(data, cfg, [call("rank_options", {**args, "sort_by": "safety"}),
                                           AIMessage(content="סידרתי")])
    cards = [d for e, d in chat(client, "תסדר לי לפי בטיחות") if e == "card"]
    assert [c["kind"] for c in cards] == ["ranking"]
    assert cards[0]["card"]["options"][0]["specs"]["nikud_betihut"]
