"""Tax Authority CSV lookups by the full key, and catalog consistency."""
from app.data.loader import VehicleKey


def test_lookup_by_full_key(data):
    # BYD Dolphin, registration 2025
    rec = data.vehicles.get(VehicleKey(2026, 2025, 1, "01014", "00012"))
    assert rec is not None
    assert rec["valueOfUse"] == 2590
    assert rec["drive"] == 3  # electric per driveField


def test_value_of_use_depends_on_registration_year(data):
    rec_2023 = data.vehicles.get(VehicleKey(2026, 2023, 1, "01014", "00012"))
    rec_2025 = data.vehicles.get(VehicleKey(2026, 2025, 1, "01014", "00012"))
    assert rec_2023["valueOfUse"] != rec_2025["valueOfUse"]


def test_car_outside_catalog_found_in_csv(data):
    # BYD Atto 2 is not in the catalog but exists at the Tax Authority
    rec = data.vehicles.get(VehicleKey(2026, 2025, 1, "01014", "00045"))
    assert rec["valueOfUse"] == 2440


def test_name_search_returns_all_candidates(data):
    # Commercial name alone is ambiguous -> several model codes
    hits = data.vehicles.search_name("MODEL Y", registration_year=2025)
    assert len({h["modelCode"] for h in hits}) > 1


def test_missing_key_returns_none(data):
    assert data.vehicles.get(VehicleKey(2026, 2025, 1, "99999", "99999")) is None


def test_every_catalog_car_matches_tax_authority(data):
    """Catalog value of use must equal the CSV value for the same full key."""
    mismatches = []
    for car in data.catalog.values():
        key = VehicleKey(
            data.vehicles.tax_year,
            car["registrationYear"],
            None,
            car["manufacturerCode"],
            car["modelCode"],
        )
        recs = data.vehicles.find(key)
        if not any(r["valueOfUse"] == car["valueOfUse"] for r in recs):
            mismatches.append((car["id"], car["valueOfUse"], [r["valueOfUse"] for r in recs]))
    assert not mismatches, mismatches


def test_drive_codes_follow_reality_not_csv_header(data):
    """CSV header says 1=electric, 2=hybrid, 3=plug-in. Reality: 3=electric, 1=hybrid, 2=plug-in."""
    dolphin = data.vehicles.get(VehicleKey(2026, 2025, 1, "01014", "00012"))
    assert dolphin["drive"] == 3 and dolphin["driveName"] == "חשמלי"


def test_drive_name_matches_catalog_for_every_catalog_car(data):
    """Independent check: the catalog's drive column agrees with our decoding of the CSV."""
    mismatches = []
    for car in data.catalog.values():
        recs = data.vehicles.find(
            VehicleKey(data.vehicles.tax_year, car["registrationYear"], None,
                       car["manufacturerCode"], car["modelCode"])
        )
        names = {r["driveName"] for r in recs if r["valueOfUse"] == car["valueOfUse"]}
        if names != {car["drive"]}:
            mismatches.append((car["id"], car["name"], car["drive"], names))
    assert not mismatches, mismatches


def test_every_csv_drive_code_is_known(data):
    unknown = {r["drive"] for r in data.vehicles.records if r["driveName"] is None}
    assert not unknown, unknown
