"""Car specs from the Ministry of Transport (data.gov.il, 'vehicle makes and models WLTP', updated daily).

Key: tozeret_cd + degem_cd + shnat_yitzur against the catalog's manufacturerCode + modelCode +
registrationYear, with leading zeros dropped ("01014" == 1014). Never by name: the same codes can
carry another commercial name (flagged as mixedModels), and a name alone matches nothing.

Several rows for one key are trim levels. Each field keeps min-max (numbers) or the list of values
(text), and variesByTrim says whether they differ.

Fuel consumption (L/100km) is computed here from CO2_WLTP with the factor in config/specs.json,
for petrol and hybrid only. Plug-in: depends on charging (WLTP CO2 assumes a charged battery).
Information only: fuel and charging are paid by the company, so nothing here enters the net.
"""
from __future__ import annotations

import json
from typing import Callable, Optional
from urllib.parse import urlencode

ELECTRIC_FUEL = "חשמל"


def normalize_code(value) -> int:
    return int(float(str(value).strip()))


def catalog_key(car: dict) -> tuple[int, int, int]:
    return (normalize_code(car["manufacturerCode"]), normalize_code(car["modelCode"]),
            normalize_code(car["registrationYear"]))


def _row_key(row: dict) -> Optional[tuple[int, int, int]]:
    try:
        return (normalize_code(row["tozeret_cd"]), normalize_code(row["degem_cd"]), normalize_code(row["shnat_yitzur"]))
    except (KeyError, TypeError, ValueError):
        return None


def query_url(catalog: dict, mot: dict) -> str:
    """One request: every code in the catalog (a superset of the exact keys, matched in code)."""
    keys = [catalog_key(c) for c in catalog.values()]
    filters = {"tozeret_cd": sorted({k[0] for k in keys}), "degem_cd": sorted({k[1] for k in keys}),
               "shnat_yitzur": sorted({k[2] for k in keys})}
    fields = ["tozeret_cd", "degem_cd", "shnat_yitzur"] + mot["fields"]
    return mot["url"] + "?" + urlencode({"resource_id": mot["resourceId"], "filters": json.dumps(filters),
                                         "fields": ",".join(fields), "limit": 5000})


def fetch_records(catalog: dict, mot: dict, get_json: Callable) -> list[dict]:
    body = get_json(query_url(catalog, mot), None)
    if not body.get("success"):
        raise RuntimeError(f"data.gov.il: {body.get('error')}")
    return body["result"]["records"]


def _field(values: list):
    present = [v for v in values if v is not None and v != ""]
    if not present:
        return None
    if all(isinstance(v, (int, float)) for v in present):
        lo, hi = min(present), max(present)
        return {"min": lo, "max": hi, "variesByTrim": lo != hi}
    distinct = sorted({str(v) for v in present})
    return {"values": distinct, "variesByTrim": len(distinct) > 1}


def _fuel(rows: list[dict], factors: dict) -> dict:
    if any("PLUG" in str(r.get("technologiat_hanaa_nm") or "").upper() for r in rows):
        return {"status": "depends_on_charging"}
    fuels = {r.get("delek_nm") for r in rows}
    if fuels == {ELECTRIC_FUEL}:
        return {"status": "not_applicable"}
    fuel = next(iter(fuels)) if len(fuels) == 1 else None
    if fuel not in factors:
        return {"status": "not_computed", "fuel": fuel if fuel is not None else "/".join(sorted(map(str, fuels)))}
    co2 = [r["CO2_WLTP"] for r in rows if isinstance(r.get("CO2_WLTP"), (int, float)) and r["CO2_WLTP"] > 0]
    if not co2:
        return {"status": "no_data"}
    per = lambda g: round(g / factors[fuel] * 100, 2)  # noqa: E731 - g CO2/km -> L/100km
    return {"status": "computed", "minL100km": per(min(co2)), "maxL100km": per(max(co2)),
            "variesByTrim": min(co2) != max(co2)}


def build_mot_specs(catalog: dict, records: list[dict], cfg: dict) -> tuple[dict, list[str]]:
    by_key: dict[tuple, list[dict]] = {}
    for r in records:
        key = _row_key(r)
        if key is not None:
            by_key.setdefault(key, []).append(r)
    specs, missing = {}, []
    for car_id, car in catalog.items():
        rows = by_key.get(catalog_key(car), [])
        if not rows:
            missing.append(car_id)
            continue
        names = {r.get("kinuy_mishari") for r in rows}
        specs[car_id] = {
            "rows": len(rows),
            "mixedModels": len(names) > 1,
            "fields": {f: _field([r.get(f) for r in rows]) for f in cfg["mot"]["fields"]},
            "fuelConsumption": _fuel(rows, cfg["fuel"]["gCo2PerLitre"]),
        }
    return specs, sorted(missing)


def load_mot(catalog: dict, cfg: dict, get_json: Callable) -> dict:
    specs, missing = build_mot_specs(catalog, fetch_records(catalog, cfg["mot"], get_json), cfg)
    return {"source": cfg["mot"]["source"], "cars": specs, "missing": missing}
