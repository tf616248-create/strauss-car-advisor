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


def calculated(advisor, args):
    """Every catalog car the employee may take, with calculate's net - computed independently."""
    out = {}
    for car in advisor.data.catalog.values():
        kind = "family_car" if car["id"] in advisor.data.rules["familyTrack"]["cars"] else "car"
        res = advisor.calculate({**args, "alternative_kind": kind, "alternative_car": car["name"]})
        if res["status"] == "ok":
            out[car["name"]] = res["card"]
    return out


def test_ranks_by_net_only_eligible_cars_with_the_same_net_as_calculate(data, cfg, store):
    opts, advisor = make(data, cfg, store)
    args = employee(data, "E-001")  # group ג, 2 children
    res = opts.rank_options(args, {}, "net")
    assert res["status"] == "ok"
    expected = calculated(advisor, args)
    best = sorted(expected, key=lambda n: -expected[n]["alternative"]["values"]["net"]["value"])[:3]
    assert [o["car"] for o in res["options"]] == best
    for o in res["options"]:
        card = expected[o["car"]]
        assert o["net"] == card["alternative"]["values"]["net"]["value"]
        assert o["diff"] == card["diff"]
        assert o["specs"]
    assert all(data.find_car(o["car"])["group"] in ("א", "ב", "ג") for o in res["options"])


def test_net_is_the_default_sort(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-001"), {}, None)["sort_by"] == "net"


def test_sort_by_safety_highest_first(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-006"), {}, "safety")  # group ד: most of the catalog
    values = [o["sort_value"]["value"] for o in res["options"]]
    assert values == sorted(values, reverse=True)
    assert res["options"][0]["car"] == "KONA EV"  # 10.5, the highest in the snapshot
    assert res["direction"] == "higher_is_safer"


def test_sort_by_pollution_lowest_first_and_cars_without_the_field_are_reported(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-006"), {}, "pollution")
    values = [o["sort_value"]["value"] for o in res["options"]]
    assert values == sorted(values)
    missing = {m["car"] for m in res["excluded_missing_data"]}
    assert ELECTRIC & missing  # no pollution group for electric cars in the source
    assert not {o["car"] for o in res["options"]} & missing


def test_the_direction_comes_from_the_config(data, cfg, store):
    specs_cfg = copy.deepcopy(load_specs_config(BACKEND_DIR))
    specs_cfg["indices"]["nikud_betihut"]["direction"] = "lower_is_safer"
    opts, _ = make(data, cfg, store, specs_cfg)
    values = [o["sort_value"]["value"] for o in opts.rank_options(employee(data, "E-006"), {}, "safety")["options"]]
    assert values == sorted(values)


def test_a_tie_is_broken_by_net(data, cfg):
    """Every car the same safety score: the order is the net order."""
    snap = snapshot_store(BACKEND_DIR)
    flat = copy.deepcopy(snap._data)
    for car in flat["mot"]["cars"].values():
        car["fields"]["nikud_betihut"] = {"min": 5, "max": 5, "variesByTrim": False}
    store = SpecsStore({name: (lambda e=e: e) for name, e in flat.items()}, BACKEND_DIR / "none.json", 24)
    store.load_all()
    opts, advisor = make(data, cfg, store)
    args = employee(data, "E-006")
    res = opts.rank_options(args, {}, "safety")
    nets = [o["net"] for o in res["options"]]
    assert nets == sorted(nets, reverse=True)
    by_net = opts.rank_options(args, {}, "net")
    assert [o["car"] for o in res["options"]] == [o["car"] for o in by_net["options"]]


def test_filters_drive_and_participation(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-001"), {"drive": ["electric"], "max_participation": 250}, "net")
    assert res["options"]
    for o in res["options"]:
        car = data.find_car(o["car"])
        assert car["name"] in ELECTRIC
        assert car["defaultParticipation"] <= 250
    assert res["applied_filters"] == {"drive": ["electric"], "max_participation": 250}


def test_min_seats_and_a_car_without_specs_is_reported(data, cfg, store):
    """David (E-002) has 5 children: the family track. SANTA FE has no official specs."""
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-002"), {"min_seats": 7}, "net")
    assert [o["car"] for o in res["options"]] == ["CARNIVAL"]
    assert {"car": "SANTA FE", "field": "mispar_moshavim", "label": "מושבים"} in res["excluded_missing_data"]


def test_flags_and_body_type(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-006"),
                            {"body_type": ["סדאן"], "adaptive_cruise": True, "reverse_camera": True}, "net")
    for o in res["options"]:
        specs = o["specs"]
        assert specs["merkav"]["value"] == "סדאן"
        assert specs["bakarat_shyut_adaptivit_ind"]["value"] is True
        assert specs["matzlemat_reverse_ind"]["value"] is True


def test_min_safety_and_power(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-006"), {"min_safety_score": 8, "min_horsepower": 250}, "net")
    for o in res["options"]:
        assert o["specs"]["nikud_betihut"]["value"] >= 8
        assert o["specs"]["koah_sus"]["value"] >= 250
    missing = {m["car"] for m in res["excluded_missing_data"]}
    assert "MODEL 3" in missing  # horsepower 0 in the source = no data


def test_no_match_says_so(data, cfg, store):
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-001"), {"min_seats": 9}, "net")
    assert res["status"] == "no_match"
    assert res["options"] == []


def test_consumption_cannot_mix_electricity_and_fuel(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-006"), {}, "consumption")["status"] == "mixed_units"
    res = opts.rank_options(employee(data, "E-006"), {"drive": ["electric"]}, "consumption")
    values = [o["sort_value"]["value"] for o in res["options"]]
    assert values == sorted(values)
    assert res["options"][0]["sort_value"]["unit"] == "Wh/km"


def test_a_car_without_participation_needs_the_rep_and_is_not_ranked(data, cfg, store, monkeypatch):
    monkeypatch.setitem(data.catalog["CAR-10"], "defaultParticipation", None)  # ATTO 3
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-001"), {"drive": ["electric"]}, "net")
    assert {"car": "ATTO 3", "fields": ["participation"]} in res["needs_rep"]
    assert "ATTO 3" not in [o["car"] for o in res["options"]]


def test_missing_employee_data_is_asked_first(data, cfg, store):
    opts, _ = make(data, cfg, store)
    args = employee(data, "E-001")
    del args["base"]
    res = opts.rank_options(args, {}, "net")
    assert res["status"] == "missing"
    assert "base" in res["fields"]


def test_an_unknown_sort_or_filter_is_invalid(data, cfg, store):
    opts, _ = make(data, cfg, store)
    assert opts.rank_options(employee(data, "E-001"), {}, "beauty")["status"] == "invalid"
    assert opts.rank_options(employee(data, "E-001"), {"trunk": 400}, "net")["status"] == "invalid"


def test_a_car_that_fails_a_filter_is_not_reported_as_missing_data(data, cfg, store):
    """MAZDA 3 has no fuel consumption, but it is petrol: an electric-only list just doesn't show it."""
    opts, _ = make(data, cfg, store)
    res = opts.rank_options(employee(data, "E-006"), {"drive": ["electric"]}, "consumption")
    assert "MAZDA 3" not in {m["car"] for m in res["excluded_missing_data"]}
