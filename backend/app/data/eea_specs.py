"""Electric consumption (Wh/km) and electric range (km) from the EEA's CO2 database (discodata SQL).

Only cars with an "eea" search key in config/car-sources.json (electric and plug-in). Search by make
(mk), commercial name (cn, partial match) and fuel type (ft), in the latest year with final data
(Status 'F'). Several versions -> min-max. Names that the partial match catches but are other models
(e.g. SEAL U, SEALION for SEAL) are left out by config/specs.json "eea.exclude".

discodata needs an alias for every selected column (error 10004), and returns {"errors": [...]}
with status 200 on a bad query - that is raised, not read as "no rows".
"""
from __future__ import annotations

import re
from typing import Callable, Optional


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def latest_final_year_sql(table: str) -> str:
    return f"SELECT MAX(Year) AS y FROM {table} WHERE Status='F'"


def car_query(key: dict, year: int, table: str, consumption: str = "[Z (Wh/km)]", rng: str = "Zr") -> str:
    like = "'%" + str(key["cn"]).replace("'", "''") + "%'"
    return (f"SELECT Cn AS cn, MIN({consumption}) AS zmin, MAX({consumption}) AS zmax, MIN({rng}) AS rmin, "
            f"MAX({rng}) AS rmax, COUNT(*) AS n FROM {table} "
            f"WHERE Year={int(year)} AND Status='F' AND Mk={_lit(key['mk'])} AND Ft={_lit(key['ft'])} "
            f"AND Cn LIKE {like} GROUP BY Cn")


def check_response(body: dict) -> list[dict]:
    if body.get("errors"):
        raise RuntimeError(f"EEA: {body['errors']}")
    return body.get("results", [])


def _run(sql: str, eea: dict, get_json: Callable) -> list[dict]:
    return check_response(get_json(eea["url"], {"query": sql, "p": 1, "nrOfHits": 500}))


def latest_final_year(eea: dict, get_json: Callable) -> int:
    return int(_run(latest_final_year_sql(eea["table"]), eea, get_json)[0]["y"])


def fetch_car(key: dict, year: int, eea: dict, get_json: Callable) -> list[dict]:
    cols = eea.get("columns", {})
    sql = car_query(key, year, eea["table"], cols.get("consumption", "[Z (Wh/km)]"), cols.get("range", "Zr"))
    return _run(sql, eea, get_json)


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


def load_eea(sources: dict, cfg: dict, get_json: Callable) -> dict:
    eea = cfg["eea"]
    year = latest_final_year(eea, get_json)
    cars, missing, verified = {}, [], {}
    for car_id, src in sources.items():
        if not src.get("eea"):
            continue
        spec = build_eea_spec(fetch_car(src["eea"], year, eea, get_json), eea["exclude"].get(car_id, []))
        verified[car_id] = spec is not None
        if spec is None:
            missing.append(car_id)
        else:
            cars[car_id] = {**spec, "year": year}
    return {"source": eea["source"], "year": year, "cars": cars, "missing": sorted(missing), "verified": verified}
