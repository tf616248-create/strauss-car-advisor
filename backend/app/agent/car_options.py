"""The logic of car_specs and rank_options (no LLM). Specs come from the specs store (Ministry of
Transport, EEA - app/data/specs_store.py); labels, directions and filters from config/specs.json
("agent", "indices").

car_specs: what is known about a catalog car. Every value carries its source, date and year; a
field without data is not shown. min == max is one value; a spec that differs between trims is a
range.

rank_options: the catalog cars the employee may take, filtered and sorted in code. Each car goes
through Advisor.calculate, so eligibility and the net are exactly calculate's. A car with a missing
spec for a filter or the sort is left out and reported; a car without catalog participation is
reported as needs_rep, outside the ranking. A tie is broken by the net, and flagged
(tie_broken_by_net). Electric cars have no pollution group in the source: they get a separate
category ("ללא פליטות מהמפלט"), first in a pollution sort - no group is invented for them.
It returns (result, card): the model reads a short result, the screen gets the card with the full
specs (the tool's artifact).
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

    def _zero_tailpipe(self, raw: dict) -> bool:
        """Electric by the Ministry of Transport: no pollution group in the source, and none is invented."""
        return self.drive_type(raw) in self.cfg["zeroTailpipe"]["drive"]

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
        if spec["field"] == "kvutzat_zihum" and self._zero_tailpipe(raw):
            return True
        v = self._value(car, raw, spec["field"], higher_is_better=False)  # op == "max"
        return None if v is None else v <= wanted

    def _direction(self, sort_by: str) -> str:
        spec = self.cfg["sortBy"][sort_by]
        return self.indices[spec["field"]]["direction"] if "directionFrom" in spec else spec["direction"]

    def _sort_key(self, car: dict, raw: dict, sort_by: str, higher: bool) -> Optional[tuple]:
        """The value the employee asked to sort by, as a key (smaller first). None = no data."""
        field = self.cfg["sortBy"][sort_by]["field"]
        if field == "kvutzat_zihum" and self._zero_tailpipe(raw):
            return (0, 0)  # before every pollution group
        v = self._value(car, raw, field, higher)
        if v is None:
            return None
        return (1, -v if higher else v)

    def _model_fields(self, car: dict, raw: dict, specs: dict, filters: dict, sort_by: str) -> dict:
        """The fields the employee filtered by, for the model: {source: {label: value}}. Grouped by source
        so each source is written once (the model reads every character). The sort field is in sort_value."""
        short = self.cfg["sourceShort"]
        mot = f'{short["mot"]}, {car["registrationYear"]}'
        sort_field = self.cfg["sortBy"][sort_by].get("field")
        out: dict[str, dict] = {}
        for name in filters:
            spec = self.cfg["filters"][name]
            field = spec.get("field", "drive")
            if field == sort_field:
                continue
            if field == "drive":
                out.setdefault(mot, {})[self.labels["technologiat_hanaa_nm"]] = self.drive_type(raw)
            elif field == "participation":
                out.setdefault(self.advisor.src["catalog"], {})[self.labels[field]] = car["defaultParticipation"]
            elif field == "kvutzat_zihum" and self._zero_tailpipe(raw):
                out.setdefault(mot, {})[self.labels[field]] = self.cfg["zeroTailpipe"]["label"]
            elif field in specs:
                item = specs[field]
                value = item["value"] if "value" in item else {"min": item["min"], "max": item["max"]}
                out.setdefault(mot, {})[item["label"]] = value
        return out

    def _sort_value(self, car: dict, raw: dict, specs: dict, card: dict, sort_by: str, higher: bool) -> dict:
        short = self.cfg["sourceShort"]
        if sort_by == "net":
            return {"value": card["alternative"]["values"]["net"]["value"], "label": "נטו משוער",
                    "source": self.advisor.src["calculation"]}
        field = self.cfg["sortBy"][sort_by]["field"]
        if field == "kvutzat_zihum" and self._zero_tailpipe(raw):
            z = self.cfg["zeroTailpipe"]
            return {"category": z["category"], "label": z["label"], "source": short["mot"]}
        out = {"value": self._value(car, raw, field, higher), "label": self.labels.get(field, field)}
        if field == "consumption":
            c = self._consumption(raw)
            electric = c[2] == "Wh/km"
            item = specs.get("electric_consumption" if electric else "fuel_consumption", {})
            out.update(unit=c[2], source=short["eea"] if electric else short["fuel"])
            if item.get("provisional"):
                out["provisional"] = True
            if item.get("year"):
                out["source"] += f', {item["year"]}'
        else:
            out["source"] = f'{short["mot"]}, {car["registrationYear"]}'
        return out

    def rank_options(self, args: dict, filters: dict, sort_by: Optional[str],
                     history: Iterable = (), thread_id: str = "default") -> tuple[dict, Optional[dict]]:
        """(result for the model, card for the screen). The model reads only the result: the names, the
        net, the diff and the fields it filtered and sorted by. The card has the full specs, and goes to
        the screen as the tool's artifact (like the comparison card), never through the model."""
        sort_by = sort_by or "net"
        filters = {k: v for k, v in (filters or {}).items() if v not in (None, [], "")}
        problem = self._invalid(filters, sort_by)
        if problem:
            return problem, None
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
                return res, None

        excluded, filtered_out, ranked = [], 0, []
        for car, kind, card in candidates:
            raw = self.store.for_car(car["id"])
            results = {name: self._passes(car, raw, name, wanted) for name, wanted in filters.items()}
            if False in results.values():  # fails a filter it has data for: simply not shown
                filtered_out += 1
                continue
            no_data = [name for name, passed in results.items() if passed is None]
            missing_field = self.cfg["filters"][no_data[0]].get("field", no_data[0]) if no_data else None
            key = None
            if missing_field is None and sort_by != "net":
                key = self._sort_key(car, raw, sort_by, higher)
                if key is None:
                    missing_field = self.cfg["sortBy"][sort_by]["field"]
            if missing_field is not None:
                label_key = "technologiat_hanaa_nm" if missing_field == "drive" else missing_field
                excluded.append({"car": car["name"], "field": missing_field,
                                 "label": self.labels.get(label_key, missing_field)})
                continue
            ranked.append((car, kind, card, raw, key))

        if sort_by == "consumption":
            units = {self._consumption(raw)[2] for _, _, _, raw, _ in ranked}
            if len(units) > 1:
                return {"status": "mixed_units", "units": sorted(units),
                        "instruction": "צריכת חשמל (Wh לק\"מ) וצריכת דלק (ליטרים) לא ניתנות להשוואה. "
                                       "שאל את העובד אם הוא מתעניין בחשמלי או ברכב על דלק, וקרא שוב עם drive."}, None

        def net(card):
            return card["alternative"]["values"]["net"]["value"]

        ranked.sort(key=lambda r: (r[4] or (), -net(r[2])))
        keys = [r[4] for r in ranked]
        options, card_options = [], []
        for i, (car, kind, card, raw, key) in enumerate(ranked[: self.cfg["top"]], start=1):
            tie = sort_by != "net" and keys.count(key) > 1  # same value as another car: the net decided
            specs = self.specs_of(car) or {}
            sort_value = self._sort_value(car, raw, specs, card, sort_by, higher)
            options.append({"rank": i, "car": car["name"], "net": net(card),
                            "diff": {k: v for k, v in card["diff"].items() if v},  # what changed
                            "sort_value": sort_value, "fields": self._model_fields(car, raw, specs, filters, sort_by),
                            "tie_broken_by_net": tie})
            card_options.append({"rank": i, "car": car["name"], "group": car["group"], "kind": kind,
                                 "participation": car["defaultParticipation"], "net": net(card),
                                 "diff": card["diff"], "sort_value": sort_value, "tie_broken_by_net": tie,
                                 "specs": specs, "importer_url": raw.get("importer_url")})

        result = {"status": "ok" if options else "no_match", "sort_by": sort_by, "direction": direction,
                  "applied_filters": filters, "options": options, "excluded_missing_data": excluded,
                  "needs_rep": needs_rep, "not_eligible": not_eligible, "filtered_out": filtered_out}
        if needs_children:
            result["family_track_needs_children"] = needs_children
        result["instruction"] = (
            "הצג בסדר הזה, עם net ו-diff.net. אמור לפי מה סידרת ואילו סינונים. המפרט המלא בכרטיס שבצד המסך."
            if options else "אף רכב לא עומד בכל הסינונים. שאל איזה סינון לרכך.")
        if not options:
            return result, None
        sort_field = self.cfg["sortBy"][sort_by].get("field")
        sort_label = self.labels.get(sort_field, sort_field) if sort_field else "נטו משוער"
        card_out = {"type": "ranking", "sort_by": sort_by, "sort_label": sort_label,
                    "direction": direction, "applied_filters": filters, "options": card_options,
                    "excluded_missing_data": excluded, "needs_rep": needs_rep}
        return result, card_out
