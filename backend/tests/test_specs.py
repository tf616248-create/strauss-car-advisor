"""Car specs layer: Ministry of Transport (data.gov.il) and EEA, with a cache and a snapshot.
No network here: the APIs are faked. Live checks are in test_specs_network.py (marker 'network')."""
import json
import logging
import re
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.data import eea_specs, mot_specs
from app.data.specs_store import SpecsStore, load_specs_config
from tests.conftest import BACKEND_DIR

SNAPSHOT = BACKEND_DIR / "cache" / "specs-snapshot.json"
SOURCES = json.loads((BACKEND_DIR / "config" / "car-sources.json").read_text(encoding="utf-8"))["cars"]


@pytest.fixture(scope="module")
def cfg():
    return load_specs_config(BACKEND_DIR)


# --- key ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["01014", "1014", 1014, 1014.0, " 01014 "])
def test_codes_are_compared_without_leading_zeros(raw):
    assert mot_specs.normalize_code(raw) == 1014


def test_catalog_key_is_manufacturer_model_year(data):
    car = data.catalog["CAR-03"]  # BYD DOLPHIN: '01014', '00012', 2025
    assert mot_specs.catalog_key(car) == (1014, 12, 2025)


def test_one_request_asks_for_every_catalog_code(data, cfg):
    url = mot_specs.query_url(data.catalog, cfg["mot"])
    assert cfg["mot"]["resourceId"] in url
    filters = json.loads(parse_qs(urlparse(url).query)["filters"][0])
    assert 1014 in filters["tozeret_cd"] and 12 in filters["degem_cd"] and 2025 in filters["shnat_yitzur"]


# --- MOT specs ---------------------------------------------------------------------


def row(**kw):
    base = {"tozeret_cd": 1014, "degem_cd": 12, "shnat_yitzur": 2025, "kinuy_mishari": "BYD DOLPHIN",
            "ramat_gimur": "DESIGN", "merkav": "האצ'בק", "mispar_moshavim": 5, "mispar_dlatot": 5, "koah_sus": 204,
            "automatic_ind": 1, "mazgan_ind": 1, "bakarat_shyut_adaptivit_ind": 1, "matzlemat_reverse_ind": 1,
            "gova": 1570, "delek_nm": "חשמל", "technologiat_hanaa_nm": "רכב חשמלי", "nikud_betihut": 9.5,
            "ramat_eivzur_betihuty": 7, "kvutzat_zihum": None, "madad_yarok": None, "CO2_WLTP": None}
    return {**base, **kw}


CATALOG = {
    "CAR-03": {"id": "CAR-03", "name": "BYD DOLPHIN", "manufacturerCode": "01014", "modelCode": "00012",
               "registrationYear": 2025},
    "CAR-07": {"id": "CAR-07", "name": "COROLLA", "manufacturerCode": "00839", "modelCode": "00295",
               "registrationYear": 2026},
    "CAR-16": {"id": "CAR-16", "name": "SPORTAGE HEV", "manufacturerCode": "00416", "modelCode": "00294",
               "registrationYear": 2026},
    "CAR-99": {"id": "CAR-99", "name": "NOWHERE", "manufacturerCode": "00001", "modelCode": "00001",
               "registrationYear": 2025},
}
PETROL = dict(tozeret_cd=839, degem_cd=295, shnat_yitzur=2026, kinuy_mishari="COROLLA", delek_nm="בנזין",
              technologiat_hanaa_nm="הנעה רגילה")


def test_every_requested_field_is_kept(cfg):
    specs, _ = mot_specs.build_mot_specs(CATALOG, [row()], cfg)
    fields = specs["CAR-03"]["fields"]
    assert set(fields) == set(cfg["mot"]["fields"])
    assert fields["koah_sus"] == {"min": 204, "max": 204, "variesByTrim": False}
    assert fields["merkav"] == {"values": ["האצ'בק"], "variesByTrim": False}


def test_trims_with_different_values_give_a_range_marked_as_varying(cfg):
    rows = [row(ramat_gimur="DESIGN", koah_sus=204), row(ramat_gimur="BOOST", koah_sus=95)]
    fields = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-03"]["fields"]
    assert fields["koah_sus"] == {"min": 95, "max": 204, "variesByTrim": True}
    assert fields["ramat_gimur"] == {"values": ["BOOST", "DESIGN"], "variesByTrim": True}
    assert fields["mispar_moshavim"]["variesByTrim"] is False


def test_codes_find_the_rows_and_only_the_catalog_name_is_kept(cfg):
    """ATTO 3's codes also carry a TANG row: TANG's data never reaches ATTO 3.
    A name alone (other codes) never matches."""
    rows = [row(kinuy_mishari="TANG", koah_sus=516), row(koah_sus=204),
            row(tozeret_cd=1, degem_cd=2, kinuy_mishari="BYD DOLPHIN", koah_sus=999)]
    specs, _ = mot_specs.build_mot_specs(CATALOG, rows, cfg)
    car = specs["CAR-03"]
    assert car["rows"] == 1
    assert car["fields"]["koah_sus"] == {"min": 204, "max": 204, "variesByTrim": False}
    assert car["otherNamesDropped"] == ["TANG"]


def test_the_name_match_ignores_case_and_spaces(cfg):
    specs, _ = mot_specs.build_mot_specs(CATALOG, [row(kinuy_mishari=" byd  dolphin ")], cfg)
    assert specs["CAR-03"]["rows"] == 1


def test_codes_without_a_row_of_the_catalog_name_give_no_specs(cfg):
    specs, missing = mot_specs.build_mot_specs(CATALOG, [row(kinuy_mishari="TANG")], cfg)
    assert "CAR-03" not in specs
    assert "CAR-03" in missing


def test_zero_or_empty_is_no_data(cfg):
    """MODEL 3: horsepower 0 in the source. Not shown, not used. Indicators (_ind) keep 0 = no."""
    fields = mot_specs.build_mot_specs(CATALOG, [row(koah_sus=0, gova=None, automatic_ind=0)], cfg)[0]["CAR-03"]["fields"]
    assert fields["koah_sus"] is None
    assert fields["gova"] is None
    assert fields["automatic_ind"] == {"min": 0, "max": 0, "variesByTrim": False}


def test_a_zero_in_one_trim_does_not_widen_the_range(cfg):
    rows = [row(koah_sus=0), row(koah_sus=204, ramat_gimur="X")]
    fields = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-03"]["fields"]
    assert fields["koah_sus"] == {"min": 204, "max": 204, "variesByTrim": False}


def test_cars_without_rows_are_listed_as_missing(cfg):
    specs, missing = mot_specs.build_mot_specs(CATALOG, [row()], cfg)
    assert "CAR-99" not in specs
    assert set(missing) == {"CAR-07", "CAR-16", "CAR-99"}


def test_petrol_consumption_comes_from_co2_and_the_configured_factor(cfg):
    factor = cfg["fuel"]["gCo2PerLitre"]["בנזין"]
    rows = [row(**PETROL, CO2_WLTP=135), row(**PETROL, CO2_WLTP=120, ramat_gimur="X")]
    fuel = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-07"]["fuelConsumption"]
    assert fuel["status"] == "computed"
    assert fuel["minL100km"] == pytest.approx(120 / factor * 100, abs=0.01)
    assert fuel["maxL100km"] == pytest.approx(135 / factor * 100, abs=0.01)
    assert fuel["variesByTrim"] is True


def test_hybrid_consumption_is_computed_too(cfg):
    rows = [row(**{**PETROL, "technologiat_hanaa_nm": "היברידי רגיל"}, CO2_WLTP=100)]
    assert mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-07"]["fuelConsumption"]["status"] == "computed"


def test_plug_in_consumption_depends_on_charging(cfg):
    rows = [row(tozeret_cd=416, degem_cd=294, shnat_yitzur=2026, kinuy_mishari="SPORTAGE HEV", delek_nm="חשמל/בנזין",
                technologiat_hanaa_nm="PLUG IN", CO2_WLTP=63)]
    fuel = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-16"]["fuelConsumption"]
    assert fuel == {"status": "depends_on_charging"}


def test_electric_has_no_fuel_and_missing_co2_is_no_data(cfg):
    specs = mot_specs.build_mot_specs(CATALOG, [row(), row(**PETROL, CO2_WLTP=None)], cfg)[0]
    assert specs["CAR-03"]["fuelConsumption"] == {"status": "not_applicable"}
    assert specs["CAR-07"]["fuelConsumption"] == {"status": "no_data"}


def test_diesel_uses_the_diesel_factor(cfg):
    """OCTAVIA: diesel in the official sources (the catalog says petrol - the specs follow the source)."""
    factor = cfg["fuel"]["gCo2PerLitre"]["דיזל"]
    rows = [row(**{**PETROL, "delek_nm": "דיזל"}, CO2_WLTP=117)]
    fuel = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-07"]["fuelConsumption"]
    assert fuel["status"] == "computed"
    assert fuel["minL100km"] == pytest.approx(117 / factor * 100, abs=0.01)


def test_a_fuel_without_a_factor_is_not_computed(cfg):
    rows = [row(**{**PETROL, "delek_nm": "גז"}, CO2_WLTP=117)]
    fuel = mot_specs.build_mot_specs(CATALOG, rows, cfg)[0]["CAR-07"]["fuelConsumption"]
    assert fuel == {"status": "not_computed", "fuel": "גז"}


def test_fuel_factors_have_a_source(cfg):
    factors = cfg["fuel"]["gCo2PerLitre"]
    assert factors["דיזל"] > factors["בנזין"] > 0
    assert "EPA" in cfg["fuel"]["source"]


def test_index_directions_have_a_source_and_are_used(cfg):
    indices = {k: v for k, v in cfg["indices"].items() if not k.startswith("_")}
    assert {k: v["direction"] for k, v in indices.items()} == {
        "nikud_betihut": "higher_is_safer", "ramat_eivzur_betihuty": "higher_is_safer",
        "kvutzat_zihum": "lower_is_cleaner", "madad_yarok": "lower_is_cleaner"}
    for name, info in indices.items():
        assert info["useForFiltering"] is True, name
        assert info["source"].startswith("https://"), name
    assert indices["kvutzat_zihum"]["range"] == [1, 15]
    assert indices["ramat_eivzur_betihuty"]["range"] == [0, 8]


# --- EEA ---------------------------------------------------------------------------


def test_every_selected_column_has_an_alias():
    """discodata: error 10004 'Please specify an alias for the first column'."""
    sql = eea_specs.car_query({"mk": "BYD", "cn": "SEAL", "ft": "electric"}, 2021, "[CO2Emission].[latest].[co2cars]")
    select = sql.split(" FROM ")[0].removeprefix("SELECT ")
    for column in select.split(", "):
        assert " AS " in column, column
    assert "Year=2021" in sql and "Status='F'" in sql
    assert "Status='P'" in eea_specs.car_query({"mk": "BYD", "cn": "SEAL", "ft": "electric"}, 2025, "[t]", status="P")
    assert "Cn LIKE '%SEAL%'" in sql and "Mk='BYD'" in sql and "Ft='electric'" in sql
    assert "[Z (Wh/km)]" in sql and "Zr" in sql


def test_quotes_in_search_values_are_escaped():
    sql = eea_specs.car_query({"mk": "O'X", "cn": "A", "ft": "electric"}, 2021, "[t]")
    assert "Mk='O''X'" in sql


def test_tables_cover_2022_to_2025_newest_first(cfg):
    tables = cfg["eea"]["tables"]
    assert [t["year"] for t in tables] == [2025, 2024, 2023, 2022]
    assert {t["status"] for t in tables} <= {"F", "P"}
    assert tables[0]["table"] == "[CO2Emission].[latest].[co2cars_2025Pv31]"
    assert cfg["eea"]["provisionalLabel"] == "נתון ראשוני"


def eea_row(cn, zmin, zmax, rmin, rmax):
    return {"cn": cn, "zmin": zmin, "zmax": zmax, "rmin": rmin, "rmax": rmax, "n": 1}


def test_versions_give_a_min_max_range():
    spec = eea_specs.build_eea_spec([eea_row("MODEL 3", 140, 166, 409, 743), eea_row("MODEL 3 / / RWD", 144, 144, 495, 495)], [])
    assert spec["consumptionWhKm"] == {"min": 140, "max": 166}
    assert spec["rangeKm"] == {"min": 409, "max": 743}
    assert spec["versions"] == ["MODEL 3", "MODEL 3 / / RWD"]


def test_seal_u_and_sealion_are_left_out():
    rows = [eea_row("SEAL", 150, 160, 500, 570), eea_row("SEAL U", 190, 200, 420, 500),
            eea_row("Seal  U DM-i", 1, 1, 1, 1), eea_row("SEALION 7", 200, 210, 400, 450)]
    spec = eea_specs.build_eea_spec(rows, ["SEAL U", "SEALION"])
    assert spec["versions"] == ["SEAL"]
    assert spec["rangeKm"] == {"min": 500, "max": 570}


def test_seal_exclusions_are_in_the_config(cfg):
    assert set(cfg["eea"]["exclude"]["CAR-17"]) == {"SEAL U", "SEALION"}


def test_no_rows_or_only_empty_values_means_no_eea_data():
    assert eea_specs.build_eea_spec([], []) is None
    assert eea_specs.build_eea_spec([eea_row("SPORTAGE", None, None, None, None)], []) is None


TABLES = [{"table": "[t2025]", "year": 2025, "status": "P"}, {"table": "[t2024]", "year": 2024, "status": "F"},
          {"table": "[t2023]", "year": 2023, "status": "F"}]


def test_each_car_gets_the_newest_year_with_data(cfg):
    sources = {"CAR-14": {"eea": {"mk": "TESLA", "cn": "MODEL 3", "ft": "electric"}},
               "CAR-03": {"eea": {"mk": "BYD", "cn": "DOLPHIN", "ft": "electric"}},
               "CAR-11": {"eea": {"mk": "KIA", "cn": "EV3", "ft": "electric"}},
               "CAR-07": {}}
    asked = []

    def get_json(url, params):
        q = params["query"]
        asked.append(q)
        if "TESLA" in q and "[t2025]" in q:
            return {"results": [eea_row("MODEL 3", 140, 166, 409, 743)]}
        if "BYD" in q and "[t2023]" in q:
            return {"results": [eea_row("DOLPHIN", 150, 160, 400, 420)]}
        return {"results": []}

    out = eea_specs.load_eea(sources, {**cfg, "eea": {**cfg["eea"], "tables": TABLES}}, get_json)
    tesla, byd = out["cars"]["CAR-14"], out["cars"]["CAR-03"]
    assert (tesla["year"], tesla["status"], tesla["provisional"]) == (2025, "P", True)
    assert (byd["year"], byd["status"], byd["provisional"]) == (2023, "F", False)
    assert out["missing"] == ["CAR-11"]
    assert out["verified"] == {"CAR-14": True, "CAR-03": True, "CAR-11": False}
    assert sum("TESLA" in q for q in asked) == 1  # stops at the first year with data


def test_an_eea_error_is_raised_not_read_as_no_rows():
    with pytest.raises(RuntimeError):
        eea_specs.check_response({"errors": [{"error": "x", "errorcode": 10004}]})


# --- cache and snapshot ------------------------------------------------------------


def write_snapshot(path):
    path.write_text(json.dumps({
        "mot": {"source": "s", "fetched_at": "2026-10-19T00:00:00+00:00", "cars": {"CAR-03": {"rows": 1}}, "missing": []},
        "eea": {"source": "e", "fetched_at": "2026-10-19T00:00:00+00:00", "cars": {}, "missing": []},
    }), encoding="utf-8")


def failing():
    raise OSError("network down")


def test_a_failing_api_falls_back_to_the_snapshot(tmp_path, caplog):
    snap = tmp_path / "specs-snapshot.json"
    write_snapshot(snap)
    store = SpecsStore({"mot": failing, "eea": lambda: {"source": "e", "cars": {"CAR-14": {"x": 1}}, "missing": []}},
                       snap, refresh_hours=24)
    with caplog.at_level(logging.INFO, logger="app.specs"):
        store.load_all()
    car = store.for_car("CAR-03")
    assert car["mot"]["origin"] == "snapshot"
    assert car["mot"]["fetched_at"] == "2026-10-19T00:00:00+00:00"
    assert car["mot"]["source"] == "s"
    assert car["mot"]["data"] == {"rows": 1}
    assert store.for_car("CAR-14")["eea"]["origin"] == "live"
    logs = " ".join(r.getMessage() for r in caplog.records)
    assert "mot: נטען מהגיבוי" in logs and "eea: נטען מה-API" in logs


def test_a_car_without_official_data_keeps_its_importer_link(tmp_path):
    """SANTA FE: not in the Ministry of Transport. No specs, the link stays, and the net is untouched."""
    store = SpecsStore({"mot": lambda: {"source": "s", "cars": {}, "missing": ["CAR-20"]}}, tmp_path / "x.json", 24,
                       links={"CAR-20": "https://www.colmobil.co.il/brands/hyundai/"})
    store.load_all()
    car = store.for_car("CAR-20")
    assert car["mot"] is None
    assert car["importer_url"] == "https://www.colmobil.co.il/brands/hyundai/"


def test_refresh_only_after_24_hours(tmp_path):
    now = [1000.0]
    calls = []

    def loader():
        calls.append(now[0])
        return {"source": "s", "cars": {}, "missing": []}

    store = SpecsStore({"mot": loader}, tmp_path / "x.json", refresh_hours=24, clock=lambda: now[0])
    assert store.refresh_if_due() is True  # never loaded
    now[0] += 23 * 3600
    assert store.refresh_if_due() is False
    now[0] += 3600
    assert store.refresh_if_due() is True
    assert len(calls) == 2


def test_background_load_does_not_hold_up_startup(tmp_path):
    release = threading.Event()

    def slow():
        release.wait(5)
        return {"source": "s", "cars": {}, "missing": []}

    store = SpecsStore({"mot": slow}, tmp_path / "x.json", refresh_hours=24)
    start = time.perf_counter()
    stop = store.start_background()
    assert time.perf_counter() - start < 0.5
    release.set()
    stop.set()


def test_the_server_starts_the_specs_store_in_the_background():
    text = (BACKEND_DIR / "app" / "api" / "server.py").read_text(encoding="utf-8")
    assert "start_background()" in text


def test_debug_mot_check_is_gone(data):
    from fastapi.testclient import TestClient

    from app.agent.advisor import load_agent_config
    from app.agent.rep_queue import InMemoryRepQueue
    from app.api.events import InMemoryNotifier
    from app.api.main import create_app
    from tests.test_agent_graph import ScriptedModel

    app = create_app(data=data, model=ScriptedModel(messages=iter([])), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=load_agent_config(BACKEND_DIR), rep_passcode=None)
    assert TestClient(app).get("/debug/mot-check").status_code == 404
    assert not (BACKEND_DIR / "app" / "api" / "debug_mot.py").exists()


# --- the snapshot in git -----------------------------------------------------------


@pytest.fixture(scope="module")
def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_is_not_in_the_data_folder():
    assert SNAPSHOT.parent.name == "cache"
    assert SNAPSHOT.exists()


def test_every_catalog_car_is_in_mot_or_listed_as_missing(snapshot, data, cfg):
    found = set(snapshot["mot"]["cars"])
    missing = set(cfg["knownMissing"]["mot"])
    assert found | missing == set(data.catalog)
    assert not found & missing
    assert set(snapshot["mot"]["missing"]) == missing


def test_every_eea_key_has_rows_or_is_listed_as_missing(snapshot, cfg):
    keys = {cid for cid, c in SOURCES.items() if c.get("eea")}
    found = set(snapshot["eea"]["cars"])
    missing = set(cfg["knownMissing"]["eea"])
    assert found | missing == keys
    assert not found & missing
    assert snapshot["eea"]["verified"] == {cid: cid in found for cid in keys}
    for car in snapshot["eea"]["cars"].values():
        assert car["provisional"] == (car["status"] == "P")


def test_atto3_in_the_snapshot_has_no_tang_data(snapshot):
    atto = snapshot["mot"]["cars"]["CAR-10"]
    assert atto["fields"]["kinuy_mishari"]["values"] == ["ATTO 3"]
    assert atto["fields"]["koah_sus"]["max"] < 516  # TANG: 516


def test_snapshot_model3_horsepower_is_no_data(snapshot):
    assert snapshot["mot"]["cars"]["CAR-14"]["fields"]["koah_sus"] is None


def test_snapshot_octavia_is_diesel_as_in_the_source(snapshot):
    octavia = snapshot["mot"]["cars"]["CAR-15"]
    assert octavia["fields"]["delek_nm"]["values"] == ["דיזל"]
    assert octavia["fuelConsumption"]["status"] == "computed"


def test_car_sources_sportage_link_and_tesla_checked_by_hand():
    assert SOURCES["CAR-16"]["importer_url"].startswith("https://kia-israel.co.il/%D7%A8%D7%9B%D7%91/%d7%a1%d7%a4")
    assert SOURCES["CAR-14"]["checked_manually"] is True


def test_snapshot_records_source_and_time(snapshot):
    for name in ("mot", "eea"):
        assert snapshot[name]["source"] and snapshot[name]["fetched_at"]
