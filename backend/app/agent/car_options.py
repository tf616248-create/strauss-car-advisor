"""The logic of car_specs and rank_options (no LLM). Specs come from the specs store (Ministry of
Transport, EEA - app/data/specs_store.py); labels, directions and filters from config/specs.json
("agent", "indices").

car_specs: what is known about a catalog car. Every value carries its source, date and year; a
field without data is not shown. min == max is one value; a spec that differs between trims is a
range.

rank_options: the catalog cars the employee may take, filtered and sorted in code. Each car goes
through Advisor.calculate, so eligibility and the net are exactly calculate's. A car with a missing
spec for a filter or the sort is left out and reported; a car without catalog participation is
reported as needs_rep, outside the ranking. A tie is broken by the net.
"""
from __future__ import annotations

from typing import Iterable, Optional

ELECTRIC_FUEL = "חשמל"
NO_OFFICIAL_DATA = "אין נתון רשמי"


def _higher_first(direction: str) -> bool:
    return direction.startswith("higher")


def _range_item(lo, hi) -> dict:
    return {"value": lo} if lo == hi else {"min": lo, "max": hi, "varies_by_trim": True}


class CarOptions:
    def __init__(self, advisor, specs_store, specs_cfg: dict):
        self.advisor = advisor
        self.data = advisor.data
        self.store = specs_store
        self.indices = specs_cfg["indices"]
        self.cfg = specs_cfg["agent"]
        self.labels = self.cfg["labels"]
        self.provisional_label = specs_cfg["eea"]["provisionalLabel"]

    # --------------------------------------------------------------- the data

    def drive_type(self, raw: dict) -> Optional[str]:
        """electric / plug_in / hybrid / petrol / diesel, from the Ministry of Transport (not the catalog)."""
        fields = ((raw.get("mot") or {}).get("data") or {}).get("fields") or {}
        fuel = set((fields.get("delek_nm") or {}).get("values") or [])
        tech = " ".join((fields.get("technologiat_hanaa_nm") or {}).get("values") or []).upper()
        if "PLUG" in tech:
            return "plug_in"
        if fuel == {ELECTRIC_FUEL}:
            return "electric"
        if "היברידי" in tech:
            return "hybrid"
        if fuel == {"דיזל"}:
            return "diesel"
        if fuel == {"בנזין"}:
            return "petrol"
        return None

    def _mot_range(self, raw: dict, field: str) -> Optional[tuple]:
        entry = ((((raw.get("mot") or {}).get("data") or {}).get("fields")) or {}).get(field)
        if not entry:
            return None
        if "values" in entry:
            return tuple(entry["values"])
        return entry["min"], entry["max"]

    def _consumption(self, raw: dict) -> Optional[tuple]:
        """(low, high, unit): electricity from EEA for electric and plug-in cars, fuel from the MOT otherwise."""
        if self.drive_type(raw) in ("electric", "plug_in"):
            m = ((raw.get("eea") or {}).get("data") or {}).get("consumptionWhKm")
            return (m["p5"], m["p95"], "Wh/km") if m and m.get("reliable") else None
        fuel = ((raw.get("mot") or {}).get("data") or {}).get("fuelConsumption") or {}
        return (fuel["minL100km"], fuel["maxL100km"], "L/100km") if fuel.get("status") == "computed" else None

    # --------------------------------------------------------- tool: car_specs

    def _base(self, entry: dict, label_key: str, year) -> dict:
        return {"label": self.labels.get(label_key, label_key), "source": entry["source"],
                "fetched_at": entry["fetched_at"], "year": year}

    def specs_of(self, car: dict) -> Optional[dict]:
        raw = self.store.for_car(car["id"])
        mot, eea = raw.get("mot"), raw.get("eea")
        if mot is None and eea is None:
            return None
        specs = {}
        if mot is not None:
            year = car["registrationYear"]
            for field, entry in mot["data"]["fields"].items():
                if entry is None or field in self.cfg["hidden"]:
                    continue
                item = self._base(mot, field, year)
                if "values" in entry:
                    vals = entry["values"]
                    item.update({"value": vals[0]} if len(vals) == 1 else {"values": vals, "varies_by_trim": True})
                elif field.endswith("_ind"):
                    item.update(_range_item(bool(entry["min"]), bool(entry["max"])))
                else:
                    item.update(_range_item(entry["min"], entry["max"]))
                specs[field] = item
            fuel = mot["data"].get("fuelConsumption") or {}
            if fuel.get("status") == "computed":
                specs["fuel_consumption"] = {**self._base(mot, "fuel_consumption", year),
                                             "source": self.cfg["fuelSource"], "unit": "L/100km", "approximate": True,
                                             **_range_item(fuel["minL100km"], fuel["maxL100km"])}
            elif fuel.get("status") == "depends_on_charging":
                specs["fuel_consumption"] = {**self._base(mot, "fuel_consumption", year),
                                             "value": self.cfg["plugInFuel"]}
        if eea is not None:
            for key, name, unit in (("consumptionWhKm", "electric_consumption", "Wh/km"),
                                    ("rangeKm", "electric_range", "km")):
                m = eea["data"].get(key)
                if not m or not m.get("reliable"):
                    continue  # an unreliable range is not shown (config: eea.maxSpreadRatio)
                item = {**self._base(eea, name, m["year"]), "unit": unit, **_range_item(m["p5"], m["p95"])}
                if m.get("provisional"):
                    item.update(provisional=True, note=self.provisional_label)
                specs[name] = item
        return specs

    def car_specs(self, name: str) -> dict:
        car = self.advisor._catalog_match(name)
        if car is None:
            return {"status": "not_in_catalog", "car": name,
                    "instruction": "יש מפרט רשמי רק לרכבים בקטלוג. אל תכתוב נתוני מפרט מהזיכרון."}
        url = self.store.for_car(car["id"]).get("importer_url")
        specs = self.specs_of(car)
        if not specs:
            return {"status": "no_official_data", "car": car["name"], "message": NO_OFFICIAL_DATA, "importer_url": url,
                    "instruction": "אמור לעובד שאין נתון רשמי על הרכב הזה, ותן את הקישור ליבואן."}
        return {"status": "ok", "car": car["name"], "specs": specs, "importer_url": url,
                "instruction": "הצג רק נתונים מכאן, עם המקור. provisional: כתוב 'נתון ראשוני'. "
                               "צריכת דלק: 'בקירוב'. בסוף: 'לפרטים המלאים: [המפרט אצל היבואן](importer_url)'."}

    # ------------------------------------------------------ tool: rank_options

    def _invalid(self, filters: dict, sort_by: str) -> Optional[dict]:
        allowed = self.cfg["filters"]
        bad = {}
        if sort_by not in self.cfg["sortBy"]:
            bad["sort_by"] = list(self.cfg["sortBy"])
        for name, value in filters.items():
            if name not in allowed:
                bad[name] = list(allowed)
            elif name == "drive" and not set(value) <= set(allowed["drive"]["values"]):
                bad[name] = allowed["drive"]["values"]
        if bad:
            return {"status": "invalid", "fields": list(bad), "options": bad,
                    "instruction": "אין סינון או מיון כזה. השתמש רק באפשרויות שב-options. "
                                   "על מה שאין עליו נתון רשמי (יופי, שקט, תא מטען) - אמור זאת לעובד."}
        return None

    def _value(self, car: dict, raw: dict, field: str, higher_is_better: bool):
        """The value every trim has: min when higher is better, max when lower is better. None = no data."""
        if field == "participation":
            return car.get("defaultParticipation")
        if field == "consumption":
            c = self._consumption(raw)
            return None if c is None else (c[0] if higher_is_better else c[1])
        r = self._mot_range(raw, field)
        if r is None:
            return None
        return r[0] if higher_is_better else r[-1]

    def _passes(self, car: dict, raw: dict, name: str, wanted) -> Optional[bool]:
        """True / False, or None when the car has no data for this filter."""
        spec = self.cfg["filters"][name]
        op = spec["op"]
        if op == "drive":
            drive = self.drive_type(raw)
            return None if drive is None else drive in wanted
        if op == "one_of":
            r = self._mot_range(raw, spec["field"])
            return None if r is None else bool(set(r) & set(wanted))
        if op == "flag":
            r = self._mot_range(raw, spec["field"])
            if r is None:
                return None
            return (r[0] == 1) if wanted else True  # every trim has it
        if op == "min":
            v = self._value(car, raw, spec["field"], higher_is_better=True)
            return None if v is None else v >= wanted
        v = self._value(car, raw, spec["field"], higher_is_better=False)  # op == "max"
        return None if v is None else v <= wanted

    def _direction(self, sort_by: str) -> str:
        spec = self.cfg["sortBy"][sort_by]
        return self.indices[spec["field"]]["direction"] if "directionFrom" in spec else spec["direction"]

    def rank_options(self, args: dict, filters: dict, sort_by: Optional[str],
                     history: Iterable = (), thread_id: str = "default") -> dict:
        sort_by = sort_by or "net"
        filters = {k: v for k, v in (filters or {}).items() if v not in (None, [], "")}
        problem = self._invalid(filters, sort_by)
        if problem:
            return problem
        direction = self._direction(sort_by)
        higher = _higher_first(direction)
        family_cars = self.data.rules["familyTrack"]["cars"]

        candidates, needs_rep, not_eligible, needs_children = [], [], 0, []
        cars = sorted(self.data.catalog.values(), key=lambda c: c["id"] in family_cars)  # regular cars first
        for car in cars:
            kind = "family_car" if car["id"] in family_cars else "car"
            res = self.advisor.calculate({**args, "alternative_kind": kind, "alternative_car": car["name"]},
                                         history=history, thread_id=thread_id)
            status = res["status"]
            if status == "ok":
                candidates.append((car, kind, res["card"]))
            elif status == "not_eligible":
                not_eligible += 1
            elif status == "needs_rep":
                needs_rep.append({"car": car["name"], "fields": res["fields"]})
            elif status == "waiting_rep" and "card" in res:
                needs_rep.append({"car": car["name"], "fields": res["fields"], "waiting_rep": True})
            elif status == "missing" and kind == "family_car" and res["fields"] == ["children"]:
                needs_children.append(car["name"])
            else:  # the employee's data or today's car: the same answer calculate would give
                return res

        excluded, filtered_out, ranked = [], 0, []
        for car, kind, card in candidates:
            raw = self.store.for_car(car["id"])
            results = {name: self._passes(car, raw, name, wanted) for name, wanted in filters.items()}
            if False in results.values():  # fails a filter it has data for: simply not shown
                filtered_out += 1
                continue
            no_data = [name for name, passed in results.items() if passed is None]
            missing_field = self.cfg["filters"][no_data[0]].get("field", no_data[0]) if no_data else None
            if missing_field is None and sort_by != "net":
                if self._value(car, raw, self.cfg["sortBy"][sort_by]["field"], higher) is None:
                    missing_field = self.cfg["sortBy"][sort_by]["field"]
            if missing_field is not None:
                label_key = "technologiat_hanaa_nm" if missing_field == "drive" else missing_field
                excluded.append({"car": car["name"], "field": missing_field,
                                 "label": self.labels.get(label_key, missing_field)})
                continue
            ranked.append((car, kind, card, raw))

        if sort_by == "consumption":
            units = {self._consumption(raw)[2] for _, _, _, raw in ranked}
            if len(units) > 1:
                return {"status": "mixed_units", "units": sorted(units),
                        "instruction": "צריכת חשמל (Wh לק\"מ) וצריכת דלק (ליטרים) לא ניתנות להשוואה. "
                                       "שאל את העובד אם הוא מתעניין בחשמלי או ברכב על דלק, וקרא שוב עם drive."}

        def net(card):
            return card["alternative"]["values"]["net"]["value"]

        def key(item):
            car, _, card, raw = item
            if sort_by == "net":
                return (-net(card),)
            v = self._value(car, raw, self.cfg["sortBy"][sort_by]["field"], higher)
            return (-v if higher else v, -net(card))

        ranked.sort(key=key)
        options = []
        for i, (car, kind, card, raw) in enumerate(ranked[: self.cfg["top"]], start=1):
            if sort_by == "net":
                sort_value = {"value": net(card), "label": "נטו משוער"}
            else:
                field = self.cfg["sortBy"][sort_by]["field"]
                sort_value = {"value": self._value(car, raw, field, higher), "label": self.labels.get(field, field)}
                if field == "consumption":
                    sort_value["unit"] = self._consumption(raw)[2]
            options.append({"rank": i, "car": car["name"], "group": car["group"], "kind": kind,
                            "participation": car["defaultParticipation"], "net": net(card), "diff": card["diff"],
                            "sort_value": sort_value, "specs": self.specs_of(car) or {},
                            "importer_url": raw.get("importer_url")})

        out = {"status": "ok" if options else "no_match", "sort_by": sort_by, "direction": direction,
               "applied_filters": filters, "options": options, "excluded_missing_data": excluded,
               "needs_rep": needs_rep, "not_eligible": not_eligible, "filtered_out": filtered_out}
        if needs_children:
            out["family_track_needs_children"] = needs_children
        out["instruction"] = (
            "סידרתי לפי הנתונים: הצג את הרכבים בסדר הזה, עם הנטו וההפרש (diff.net) מהתוצאה בלבד. "
            "אמור בגלוי לפי מה מיינת ואילו סינונים הפעלת. רכבים ב-excluded_missing_data הוצאו כי חסר להם "
            "נתון רשמי - ציין זאת. רכבים ב-needs_rep לא נכנסו לדירוג. "
            "אל תכתוב 'שטראוס ממליצה' או 'הכי טוב לך'."
            if options else
            "אף רכב שמגיע לעובד לא עומד בכל הסינונים. אמור זאת, ושאל איזה סינון אפשר לרכך.")
        return out
