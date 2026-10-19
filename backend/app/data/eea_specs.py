"""Electric consumption (Wh/km) and electric range (km) from the EEA's CO2 database (discodata SQL).

Only cars with an "eea" search key in config/car-sources.json (electric and plug-in). Search by make
(mk), commercial name (cn, partial match) and fuel type (ft). Names the partial match catches but are
other models (DOLPHIN SURF for DOLPHIN; SEAL U, SEALION, SEAL 6 for SEAL) are left out by
config/specs.json "eea.exclude".

Each row in EEA is one registration, and some are junk (15 Wh/km - a kWh/100km unit error - or a
range value in the consumption column). So a measure is not min-max but the P5-P95 of the values,
weighted by how many registrations have each value. If P95 > maxSpreadRatio x P5 the measure is
unreliable ("טווח לא אמין") and is not shown.

The tables (eea.tables, 2022-2025) are tried newest first, separately for each measure: a measure
takes the newest year where it is reliable. If no year is, it keeps the newest one with data,
marked reliable=false. Provisional data (Status 'P') is marked provisional=true ("נתון ראשוני").

discodata needs an alias for every selected column (error 10004), and returns {"errors": [...]}
with status 200 on a bad query - that is raised, not read as "no rows".
"""
from __future__ import annotations

import re
from typing import Callable, Optional

PAGE_SIZE = 500


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def distribution_query(key: dict, table: dict, column: str) -> str:
    """How many registrations have each value of column, per commercial name."""
    like = "'%" + str(key["cn"]).replace("'", "''") + "%'"
    return (f"SELECT Cn AS cn, {column} AS v, COUNT(*) AS n FROM {table['table']} "
            f"WHERE Year={int(table['year'])} AND Status={_lit(table['status'])} AND Mk={_lit(key['mk'])} "
            f"AND Ft={_lit(key['ft'])} AND Cn LIKE {like} GROUP BY Cn, {column}")


def check_response(body: dict) -> list[dict]:
    if body.get("errors"):
        raise RuntimeError(f"EEA: {body['errors']}")
    return body.get("results", [])


def fetch_distribution(key: dict, table: dict, column: str, eea: dict, get_json: Callable,
                       page_size: int = PAGE_SIZE) -> list[dict]:
    sql, rows, page = distribution_query(key, table, column), [], 1
    while True:
        got = check_response(get_json(eea["url"], {"query": sql, "p": page, "nrOfHits": page_size}))
        rows += got
        if len(got) < page_size:
            return rows
        page += 1


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip().upper()


def keep_rows(rows: list[dict], exclude: list[str]) -> list[dict]:
    excluded = [_norm(x) for x in exclude]
    return [r for r in rows if not any(x in _norm(r.get("cn")) for x in excluded)]


def weighted_percentile(pairs: list[tuple], p: float) -> Optional[float]:
    """pairs: (value, registrations). None and 0 are not values."""
    values = sorted((v, n) for v, n in pairs if v)
    total = sum(n for _, n in values)
    if not total:
        return None
    seen = 0
    for v, n in values:
        seen += n
        if seen >= p / 100 * total:
            return v
    return values[-1][0]


def measure(pairs: list[tuple], eea: dict) -> Optional[dict]:
    lo_p, hi_p = eea["percentiles"]
    lo, hi = weighted_percentile(pairs, lo_p), weighted_percentile(pairs, hi_p)
    if lo is None:
        return None
    return {"p5": lo, "p95": hi, "ratio": round(hi / lo, 2), "reliable": hi <= eea["maxSpreadRatio"] * lo,
            "registrations": sum(n for v, n in pairs if v)}


COLUMNS = {"consumptionWhKm": ("consumption", "[Z (Wh/km)]"), "rangeKm": ("range", "Zr")}


def _find_measure(key: dict, exclude: list[str], name: str, eea: dict, get_json: Callable) -> Optional[dict]:
    cfg_name, default = COLUMNS[name]
    column = eea.get("columns", {}).get(cfg_name, default)
    fallback = None
    for table in eea["tables"]:
        rows = keep_rows(fetch_distribution(key, table, column, eea, get_json), exclude)
        m = measure([(r["v"], r["n"]) for r in rows], eea)
        if m is None:
            continue
        m = {**m, "year": table["year"], "status": table["status"], "provisional": table["status"] == "P",
             "versions": sorted({r["cn"] for r in rows if r["v"]})}
        if m["reliable"]:
            return m
        fallback = fallback or m
    return fallback


def find_car(key: dict, exclude: list[str], eea: dict, get_json: Callable) -> Optional[dict]:
    spec = {name: _find_measure(key, exclude, name, eea, get_json) for name in COLUMNS}
    return spec if any(spec.values()) else None


def load_eea(sources: dict, cfg: dict, get_json: Callable) -> dict:
    eea = cfg["eea"]
    cars, missing, verified = {}, [], {}
    for car_id, src in sources.items():
        if not src.get("eea"):
            continue
        spec = find_car(src["eea"], eea["exclude"].get(car_id, []), eea, get_json)
        verified[car_id] = spec is not None
        if spec is None:
            missing.append(car_id)
        else:
            cars[car_id] = spec
    return {"source": eea["source"], "cars": cars, "missing": sorted(missing), "verified": verified}
