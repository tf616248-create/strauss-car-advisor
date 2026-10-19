"""Electric consumption (Wh/km) and electric range (km) from the EEA's CO2 database (discodata SQL).

Only cars with an "eea" search key in config/car-sources.json (electric and plug-in). Search by make
(mk), commercial name (cn, partial match) and fuel type (ft). The tables (config/specs.json
"eea.tables", 2022-2025) are tried newest first, and each car gets the newest year that has data.
Provisional data (Status 'P') is marked provisional=true, shown as "נתון ראשוני". Several versions ->
min-max. Names the partial match catches but are other models (SEAL U, SEALION for SEAL) are left
out by "eea.exclude".

discodata needs an alias for every selected column (error 10004), and returns {"errors": [...]}
with status 200 on a bad query - that is raised, not read as "no rows".
"""
from __future__ import annotations

import re
from typing import Callable, Optional


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def car_query(key: dict, year: int, table: str, consumption: str = "[Z (Wh/km)]", rng: str = "Zr",
              status: str = "F") -> str:
    like = "'%" + str(key["cn"]).replace("'", "''") + "%'"
    return (f"SELECT Cn AS cn, MIN({consumption}) AS zmin, MAX({consumption}) AS zmax, MIN({rng}) AS rmin, "
            f"MAX({rng}) AS rmax, COUNT(*) AS n FROM {table} "
            f"WHERE Year={int(year)} AND Status={_lit(status)} AND Mk={_lit(key['mk'])} AND Ft={_lit(key['ft'])} "
            f"AND Cn LIKE {like} GROUP BY Cn")


def check_response(body: dict) -> list[dict]:
    if body.get("errors"):
        raise RuntimeError(f"EEA: {body['errors']}")
    return body.get("results", [])


def fetch_car(key: dict, table: dict, eea: dict, get_json: Callable) -> list[dict]:
    """table: one entry of eea.tables - {"table", "year", "status"}."""
    cols = eea.get("columns", {})
    sql = car_query(key, table["year"], table["table"], cols.get("consumption", "[Z (Wh/km)]"),
                    cols.get("range", "Zr"), table["status"])
    return check_response(get_json(eea["url"], {"query": sql, "p": 1, "nrOfHits": 500}))


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip().upper()


def _range(rows: list[dict], lo: str, hi: str) -> Optional[dict]:
    los = [r[lo] for r in rows if r.get(lo) is not None]
    his = [r[hi] for r in rows if r.get(hi) is not None]
    return {"min": min(los), "max": max(his)} if los and his else None


def build_eea_spec(rows: list[dict], exclude: list[str]) -> Optional[dict]:
    excluded = [_norm(x) for x in exclude]
    kept = [r for r in rows if not any(x in _norm(r.get("cn")) for x in excluded)]
    consumption, rng = _range(kept, "zmin", "zmax"), _range(kept, "rmin", "rmax")
    if consumption is None and rng is None:
        return None
    return {"consumptionWhKm": consumption, "rangeKm": rng, "versions": sorted({r["cn"] for r in kept})}


def find_car(key: dict, exclude: list[str], eea: dict, get_json: Callable) -> Optional[dict]:
    """The newest table with data for this car, or None."""
    for table in eea["tables"]:
        spec = build_eea_spec(fetch_car(key, table, eea, get_json), exclude)
        if spec is not None:
            return {**spec, "year": table["year"], "status": table["status"], "provisional": table["status"] == "P"}
    return None


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
