"""The guards behind the agent's 4 tools. No LLM here - plain functions over the data.

Every method returns a dict with a `status`:
  ok | missing | invalid | contradiction | not_eligible | ambiguous | not_found
  | needs_rep | waiting_rep | sent | not_for_rep
Only `ok` (and the known half of `waiting_rep`) carries calculated numbers.

When to ask the rep is decided here; the thresholds live in config/agent.json.
Attempts are counted from the conversation history (earlier tool results), so the
tools stay stateless.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional

from app import profile as profile_mod
from app.engine.net import compute_net
from app.engine.scenario import Choice, EmployeeInput, build_scenario
from app.payslip import fields_of
from app.profile import PROFILE_FIELDS, OccupationMatcher

KINDS = ("car", "family_car", "waiver")
NUMERIC_FIELDS = ("base", "commission", "bonus", "pension_pct", "keren_pct", "credit_points",
                  "children", "current_participation")
EMPLOYEE_FIELDS = ("occupation", "group", "base", "commission", "bonus", "pension_pct", "keren_pct",
                   "credit_points", "children", "current_participation")
# Company information about a car outside the catalog - only the rep knows it.
COMPANY_FIELDS = ("carGroup", "companyCost", "participation")
DIFF_KEYS = ("value_of_use", "participation", "electric_refund_net", "maintenance", "family_share",
             "tax", "social", "net")
FAILED = ("not_found", "ambiguous", "needs_rep")
log = logging.getLogger(__name__)


def load_agent_config(base_dir: Path) -> dict:
    return json.loads((Path(base_dir) / "config" / "agent.json").read_text(encoding="utf-8"))


def _shekel(x: float) -> int:
    """Display rounding (rules v2: round only for display)."""
    return int(math.floor(x + 0.5))


def _results(history: Iterable, names: tuple[str, ...]) -> list[dict]:
    out = []
    for msg in history:
        if getattr(msg, "type", None) == "tool" and getattr(msg, "name", None) in names:
            try:
                out.append(json.loads(msg.content))
            except (TypeError, ValueError):
                continue
    return out


class Advisor:
    CALCULATE_FIELDS = (
        "occupation", "group", "base", "commission", "bonus", "pension_pct", "keren_pct",
        "credit_points", "children", "current_kind", "current_car", "current_car_year",
        "current_participation", "alternative_kind", "alternative_car", "alternative_car_year",
    )
    ELIGIBILITY_FIELDS = ("occupation", "group", "children", "alternative_kind", "alternative_car",
                          "alternative_car_year")

    def __init__(self, data, rep_queue, cfg: dict, profiles=None):
        """profiles: the employees' profiles (app/profile.py, app/db.py); None = no profiles (the console,
        most tests). The tools get the employee id from the run config."""
        self.data = data
        self.queue = rep_queue
        self.cfg = cfg
        self.profiles = profiles
        self.matcher = OccupationMatcher(data.occupations, cfg["profile"]["maxSuggestions"])
        self.src = cfg["texts"]["sources"]
        self.pending_text = cfg["texts"]["pending"]

    # --------------------------------------------------------------- profile

    def _profile(self, employee_id: Optional[str]) -> dict:
        if self.profiles is None or not employee_id:
            return {}
        return self.profiles.get(employee_id)

    def _save_profile(self, employee_id: Optional[str], values: dict, updated: list) -> None:
        """The employee wrote a new value in the chat: it goes to the profile (the latest value wins)."""
        if not values or self.profiles is None or not employee_id:
            return
        try:
            self.profiles.update(employee_id, values)
        except Exception:  # noqa: BLE001 - the answer matters more than the profile
            log.exception("could not update the profile of %s", employee_id)
            return
        profile_mod.trace_profile("profile_updated", sorted(values))
        updated.extend(f for f in values if f not in updated)

    def _with_profile(self, res: dict, updated: list) -> dict:
        """The tool's result, and what Kobi says when the profile changed ("עדכנתי בפרופיל")."""
        if updated:
            t = self.cfg["texts"]["profile"]
            res["profile_updated"] = list(updated)
            res["message_profile"] = t["updated"].format(fields=", ".join(t["labels"][f] for f in updated))
        return res

    # ------------------------------------------------- tool: occupation_to_group

    def occupation_to_group(self, occupation: str, employee_id: Optional[str] = None) -> dict:
        found = self.matcher.find(occupation)
        if found["status"] != "ok":
            return {"status": "not_found", "suggestions": found["suggestions"],
                    "instruction": "העיסוק לא נמצא בטבלת העיסוקים. שאל את העובד מה העיסוק שלו, והצע לו את "
                                   "suggestions. אל תנחש עיסוק או קבוצה."}
        updated = []
        if found["occupation"] != self._profile(employee_id).get("occupation"):
            self._save_profile(employee_id, {"occupation": found["occupation"]}, updated)
        return self._with_profile({**found, "source": self.src["occupation"]}, updated)

    # ------------------------------------------------------------------ cars

    def _catalog_match(self, name: str) -> Optional[dict]:
        car = self.data.find_car(name)
        if car:
            return car
        q = f" {name.strip().upper()} "
        hits = [c for c in self.data.catalog.values() if f" {c['name'].upper()} " in q]
        return hits[0] if len(hits) == 1 else None

    def _resolve_car(self, name: str, year: Optional[int] = None, model_code: Optional[str] = None):
        """('catalog', car) | ('tax', car) | ('ambiguous', candidates) | ('not_found', None)."""
        car = self._catalog_match(name)
        if car:
            return "catalog", car
        hits = self.data.vehicles.search_name(name, registration_year=year)
        if model_code:
            hits = [h for h in hits if h["modelCode"] == str(model_code).strip()]
        distinct = {}
        for h in hits:
            distinct.setdefault((h["registrationYear"], h["manufacturerCode"], h["modelCode"], h["valueOfUse"]), h)
        if not distinct:
            return "not_found", None
        if len(distinct) > 1:
            cands = [
                {"name": h["name"], "registrationYear": h["registrationYear"], "modelCode": h["modelCode"],
                 "modelDescription": h["modelDescription"]}
                for h in list(distinct.values())[: self.cfg["maxCandidates"]]
            ]
            return "ambiguous", cands
        rec = next(iter(distinct.values()))
        return "tax", {
            "id": None,
            "key": f'{rec["manufacturerCode"]}/{rec["modelCode"]}/{rec["registrationYear"]}',
            "name": rec["name"],
            "registrationYear": rec["registrationYear"],
            "valueOfUse": rec["valueOfUse"],
            "drive": rec["driveName"],
            "manufacturerCode": rec["manufacturerCode"],
            "modelCode": rec["modelCode"],
            "modelDescription": rec["modelDescription"],
            "group": None,
            "companyCost": None,
            "defaultParticipation": None,
        }

    def _car_key(self, kind: str, car: dict) -> str:
        return car["id"] if kind == "catalog" else car["key"]

    # ---------------------------------------------------------- tool: lookup

    def lookup_vehicle(self, name: str, registration_year: Optional[int] = None,
                       model_code: Optional[str] = None, history: Iterable = ()) -> dict:
        kind, found = self._resolve_car(name, registration_year, model_code)
        if kind == "catalog":
            return {"status": "ok", "car": {
                "name": found["name"], "registrationYear": found["registrationYear"],
                "valueOfUse": found["valueOfUse"], "drive": found["drive"], "group": found["group"],
                "companyCost": found["companyCost"], "defaultParticipation": found["defaultParticipation"],
                "inCatalog": True, "source": self.src["catalog"]}}
        if kind == "tax":
            return {
                "status": "ok",
                "car": {"name": found["name"], "registrationYear": found["registrationYear"],
                        "modelCode": found["modelCode"], "valueOfUse": found["valueOfUse"],
                        "drive": found["drive"], "inCatalog": False, "source": self.src["taxAuthority"]},
                "companyFields": list(COMPANY_FIELDS),
                "instruction": "הרכב לא בקטלוג. אם זו החלופה: הקבוצה, העלות וההשתתפות הן מידע של החברה. "
                               "אל תשאל את העובד - קרא ל-ask_rep עם השדות האלה.",
            }

        # failed: count consecutive failures since the last successful lookup
        failures = 0
        for res in _results(history, ("lookup_vehicle",)):
            failures = failures + 1 if res.get("status") in FAILED else 0
        if failures + 1 >= self.cfg["maxAttempts"]:
            return {"status": "needs_rep", "fields": ["car"],
                    "instruction": "הרכב לא זוהה גם אחרי ניסיון חוזר. קרא ל-ask_rep עם השדה car."}
        if kind == "ambiguous":
            return {"status": "ambiguous", "candidates": found,
                    "instruction": "יש כמה גרסאות. שאל את העובד על שנת הרישום או הגרסה, "
                                   "ואז קרא שוב עם registration_year או model_code."}
        return {"status": "not_found",
                "instruction": "הרכב לא נמצא. בקש מהעובד את השם המסחרי המדויק (למשל ATTO 2) ושנת רישום."}

    # ------------------------------------------------------- shared checks

    def _required(self, args: dict, for_calculate: bool) -> list[str]:
        req = ["occupation", "group"]
        if for_calculate:
            req += ["base", "commission", "bonus", "pension_pct", "keren_pct", "credit_points", "current_kind"]
            if args.get("current_kind") == "car":
                req += ["current_car", "current_participation"]
        req.append("alternative_kind")
        if args.get("alternative_kind") in ("car", "family_car"):
            req.append("alternative_car")
        if args.get("alternative_kind") == "family_car":
            req.append("children")
        return req

    def _invalid(self, args: dict) -> tuple[list[str], dict]:
        bad, options = [], {}
        for field, (lo, hi) in self.cfg["ranges"].items():
            if args.get(field) is None:
                continue
            try:
                ok = lo <= float(args[field]) <= hi
            except (TypeError, ValueError):
                ok = False
            if not ok:
                bad.append(field)
        if args.get("occupation") is not None and args["occupation"] not in self.data.occupations:
            bad.append("occupation")  # the closest ones from the sheet, to ask about (never a guess)
            options["occupation"] = self.matcher.find(args["occupation"])["suggestions"]
        if args.get("group") is not None and args["group"] not in self.data.rules["groupOrder"]:
            bad.append("group")
            options["group"] = list(self.data.rules["groupOrder"])
        for field in ("current_kind", "alternative_kind"):
            if args.get(field) is not None and args[field] not in KINDS:
                bad.append(field)
                options[field] = list(KINDS)
        if args.get("current_kind") == "family_car":
            bad.append("current_kind")
            options["current_kind"] = ["car", "waiver"]
        return bad, options

    def _where_to_find(self, fields: list[str], history) -> str:
        counts = defaultdict(int)
        for res in _results(history, ("calculate", "check_eligibility")):
            if res.get("status") in ("invalid", "missing"):
                for f in res.get("fields", []):
                    counts[f] += 1
        if any(counts[f] + 1 >= self.cfg["maxAttempts"] for f in fields):
            return (" זו כבר הפעם השנייה: אמור לעובד שהנתונים האלה מופיעים בתלוש השכר שלו. "
                    "אל תנחש, ואל תפנה לנציג - הנציג לא יודע את נתוני השכר של העובד.")
        return ""

    def _check_employee(self, args: dict, history, thread_id: str, for_calculate: bool,
                        employee_id: Optional[str] = None, updated: Optional[list] = None):
        """Apply rep answers, the profile and the payslip, then validate. Returns (problem | None, args, sources).
        updated: gets the profile fields this call changed (a new value the employee wrote)."""
        updated = updated if updated is not None else []
        answers = self.queue.answers(thread_id)
        pending = self.queue.pending_fields(thread_id)
        args = {k: v for k, v in args.items() if v not in (None, "")}
        if "occupation" in args and args["occupation"] not in self.data.occupations:
            found = self.matcher.find(args["occupation"])  # as the employee wrote it: "מנהלת אזור המכירות"
            if found["status"] == "ok":
                args["occupation"] = found["occupation"]
        # Filled in code, never by the model: the profile (this employee's, in every conversation),
        # then an uploaded payslip (app/payslip.py). What the model passes wins - the employee may have
        # corrected it; and a payslip uploaded through the API has already updated the profile.
        profile = self._profile(employee_id)
        payslip = fields_of(history)
        # another car than the profile's: its year and participation are not the profile's
        new_car = "current_car" in args and args["current_car"] != profile.get("current_car")
        sources = {}
        for field in EMPLOYEE_FIELDS + ("current_kind", "current_car", "current_car_year"):
            if (field, None) in answers:
                args[field] = answers[(field, None)]
                sources[field] = self.src["rep"]
            elif field in args:
                sources[field] = self.src["employee"]
            elif field in profile and not (new_car and field in ("current_car_year", "current_participation")):
                args[field] = profile[field]
                # the payslip of this conversation is where the profile got it: say so
                same = field in payslip and payslip[field] == profile[field]
                sources[field] = self.src["payslip" if same else "profile"]
            elif field in payslip:
                args[field] = payslip[field]
                sources[field] = self.src["payslip"]
        # the group comes from the occupation (the sheet), in code - unless the employee stated one
        if "group" not in args and args.get("occupation") in self.data.occupations:
            args["group"] = self.data.occupations[args["occupation"]]["group"]
            sources["group"] = self.src["occupation"]

        bad, options = self._invalid(args)
        new = {f: args[f] for f in PROFILE_FIELDS
               if sources.get(f) == self.src["employee"] and f not in bad and args[f] != profile.get(f)}
        self._save_profile(employee_id, new, updated)
        waiting = [f for f in bad if (f, None) in pending]
        if waiting:
            return self._waiting(waiting), args, sources
        # Employee data stays with the employee: the rep cannot know an anonymous
        # employee's salary. After the second failed attempt, say where to find it.
        if bad:
            res = {"status": "invalid", "fields": bad,
                   "instruction": "הערכים לא תקינים. שאל את העובד שוב על השדות האלה."
                                  + self._where_to_find(bad, history)}
            if options:
                res["options"] = options
            return res, args, sources

        missing = [f for f in self._required(args, for_calculate) if f not in args]
        waiting = [f for f in missing if (f, None) in pending]
        if waiting:
            return self._waiting(waiting), args, sources
        if missing:
            res = {"status": "missing", "fields": missing,
                   "instruction": "חסר מידע. שאל את העובד על השדות האלה, אל תנחש."
                                  + self._where_to_find(missing, history)}
            # many details missing (linkWhenMissing): the profile page and the payslip, not one by one
            from_profile = [f for f in missing if f in PROFILE_FIELDS]
            if (self.profiles is not None and employee_id
                    and len(from_profile) >= self.cfg["profile"]["linkWhenMissing"]):
                res["profile_link"] = self.cfg["profile"]["link"]
                res["message_to_employee"] = self.cfg["texts"]["profile"]["link"]
                res["instruction"] = ("חסרים כמה נתונים. אל תשאל עליהם אחד-אחד: כתוב לעובד את "
                                      "message_to_employee כמו שהוא.")
            return res, args, sources

        occ_group = self.data.occupations[args["occupation"]]["group"]
        if ("group", None) not in answers and args["group"] != occ_group:
            if ("group", None) in pending:
                return self._waiting(["group"]), args, sources
            return {"status": "contradiction", "field": "group", "employee_group": args["group"],
                    "occupation_group": occ_group,
                    "instruction": "כתוב לעובד שלפי העיסוק שלו הקבוצה היא occupation_group. "
                                   "אם הוא מתעקש, קרא ל-ask_rep עם השדה group."}, args, sources
        return None, args, sources

    def _waiting(self, fields: list[str]) -> dict:
        return {"status": "waiting_rep", "fields": fields,
                "instruction": "כבר נשלחה שאלה לנציג על השדות האלה. אמור לעובד שהתשובה תתעדכן."}

    def _resolve_choice(self, args: dict, prefix: str, thread_id: str):
        """Resolve current_/alternative_ car. Returns (problem | None, Choice, car, car_sources, pending_keys)."""
        kind = args[f"{prefix}_kind"]
        if kind == "waiver":
            return None, Choice.waiver(), None, {}, []
        name, year = args[f"{prefix}_car"], args.get(f"{prefix}_car_year")
        found_kind, car = self._resolve_car(name, year)
        if found_kind in ("ambiguous", "not_found"):
            res = {"status": found_kind, "which": prefix, "car": name,
                   "instruction": "הרכב לא זוהה בוודאות. קרא ל-lookup_vehicle ושאל את העובד שנה או גרסה."}
            if found_kind == "ambiguous":
                res["candidates"] = car
            return res, None, None, {}, []

        key = self._car_key(found_kind, car)
        source = self.src["catalog"] if found_kind == "catalog" else self.src["taxAuthority"]
        car_sources = {"value_of_use": source, "car_cost": source}
        pending_keys = []
        participation = None

        if prefix == "current":
            participation = args["current_participation"]
            car_sources["participation"] = self.src["employee"]
            if found_kind == "tax":
                car_sources["car_cost"] = None
        else:
            answers = self.queue.answers(thread_id)
            pending = self.queue.pending_fields(thread_id)
            car = dict(car)
            needed = list(COMPANY_FIELDS) if found_kind == "tax" else (
                ["participation"] if car.get("defaultParticipation") is None else [])
            car_sources["participation"] = self.src["catalog"]
            target = {"carGroup": "group", "companyCost": "companyCost", "participation": "defaultParticipation"}
            for field in needed:
                if (field, key) in answers:
                    car[target[field]] = answers[(field, key)]
                    car_sources["car_cost" if field == "companyCost" else field] = self.src["rep"]
                elif (field, key) in pending:
                    pending_keys.append(field)
                else:
                    return ({"status": "needs_rep", "fields": [f for f in needed if (f, key) not in answers],
                             "car": car["name"], "registration_year": car["registrationYear"],
                             "instruction": "זה מידע של החברה שהעובד לא יכול לדעת. קרא ל-ask_rep עם השדות "
                                            "והרכב האלה. אל תשאל את העובד."},
                            None, car, car_sources, [])
            if found_kind == "tax":
                car_sources["participation"] = self.src["rep"]
            participation = car["defaultParticipation"]

        choice_kind = "car" if kind == "car" else "family_car"
        choice = Choice(choice_kind, car_ref=car["name"], participation=participation,
                        car_record=car if found_kind == "tax" else None)
        return None, choice, car, car_sources, pending_keys

    def _employee_input(self, args: dict) -> EmployeeInput:
        return EmployeeInput(
            occupation=args["occupation"], group=args["group"],
            base=float(args.get("base", 0)), commission=float(args.get("commission", 0)),
            bonus=float(args.get("bonus", 0)), pension_pct=float(args.get("pension_pct", 0)),
            keren_pct=float(args.get("keren_pct", 0)), credit_points=float(args.get("credit_points", 0)),
            children=int(args.get("children", 0)),
        )

    def _reason(self, code: str, details: dict, emp: EmployeeInput) -> str:
        fmt = defaultdict(str, details)
        fmt.setdefault("employeeGroup", emp.group)
        fmt.setdefault("occupation", emp.occupation)
        fmt.setdefault("children", emp.children)
        return self.cfg["texts"]["reasons"].get(code, code).format_map(fmt)

    # ----------------------------------------------------- tool: eligibility

    def check_eligibility(self, args: dict, history: Iterable = (), thread_id: str = "default",
                          employee_id: Optional[str] = None) -> dict:
        updated = []
        return self._with_profile(self._check_eligibility(args, history, thread_id, employee_id, updated), updated)

    def _check_eligibility(self, args, history, thread_id, employee_id, updated) -> dict:
        args = {k: args.get(k) for k in self.ELIGIBILITY_FIELDS}
        problem, args, _ = self._check_employee(args, history, thread_id, False, employee_id, updated)
        if problem:
            return problem
        problem, choice, _, _, pending = self._resolve_choice(args, "alternative", thread_id)
        if problem:
            return problem
        if "carGroup" in pending:
            return self._waiting(["carGroup"])
        emp = self._employee_input(args)
        res = build_scenario(emp, choice, self.data)
        return {"status": "ok", "eligible": res.eligible, "reason_code": res.reason_code,
                "reason": self._reason(res.reason_code, res.details, emp)}

    # ------------------------------------------------------- tool: calculate

    def calculate(self, args: dict, history: Iterable = (), thread_id: str = "default",
                  employee_id: Optional[str] = None) -> dict:
        """employee_id: whose profile fills in what the model did not pass (None: no profile)."""
        updated = []
        return self._with_profile(self._calculate(args, history, thread_id, employee_id, updated), updated)

    def _calculate(self, args, history, thread_id, employee_id, updated) -> dict:
        args = {k: args.get(k) for k in self.CALCULATE_FIELDS}
        problem, args, emp_sources = self._check_employee(args, history, thread_id, True, employee_id, updated)
        if problem:
            return problem
        problem, today_choice, today_car, today_src, _ = self._resolve_choice(args, "current", thread_id)
        if problem:
            return problem
        problem, alt_choice, alt_car, alt_src, pending = self._resolve_choice(args, "alternative", thread_id)
        if problem:
            return problem

        emp = self._employee_input(args)
        today_res = build_scenario(emp, today_choice, self.data, is_current=True)
        today = self._side(emp, today_res, today_car, today_src, "today", args["current_kind"])

        if pending:
            alt_side = self._pending_side(alt_choice, alt_car, alt_src)
            return {"status": "waiting_rep", "fields": pending,
                    "card": self._card(args, emp_sources, today, alt_side, None),
                    "instruction": "חלק מהנתונים ממתינים לנציג. הצג את מה שידוע, ואמור שהחלופה תתעדכן."}

        alt_res = build_scenario(emp, alt_choice, self.data)
        if not alt_res.eligible:
            return {"status": "not_eligible", "reason_code": alt_res.reason_code,
                    "reason": self._reason(alt_res.reason_code, alt_res.details, emp)}
        alt = self._side(emp, alt_res, alt_car, alt_src, alt_res.reason_code, args["alternative_kind"])
        diff = {k: alt["values"][k]["value"] - today["values"][k]["value"] for k in DIFF_KEYS}
        return {"status": "ok", "card": self._card(args, emp_sources, today, alt, diff)}

    def _side(self, emp, res, car, car_sources: dict, reason_code: str, kind: str) -> dict:
        rules = self.data.rules
        scen = res.scenario
        nb = compute_net(emp, scen, rules)
        is_car = car is not None
        refund_net = rules["electric"]["netBonus"] if scen.electric else 0
        v = {
            "value_of_use": (scen.value_of_use, car_sources.get("value_of_use") if is_car else self.src["rules"]),
            "participation": (scen.participation, car_sources.get("participation") if is_car else self.src["rules"]),
            "electric_refund_net": (refund_net, self.src["rules"]),
            "electric_refund_gross": (nb.electric_gross, self.src["rules"]),
            "maintenance": (scen.maintenance, self.src["occupation"]),
            "family_share": (nb.family_share, self.src["rules"]),
            "budget": (rules["budgets"][emp.group], self.src["rules"]),
            "car_cost": ((car or {}).get("companyCost") if is_car else 0,
                         car_sources.get("car_cost") if is_car else self.src["rules"]),
            "tax": (nb.tax, self.src["calculation"]),
            "social": (nb.social, self.src["calculation"]),
            "net": (nb.net, self.src["calculation"]),
        }
        values = {k: {"value": None if x is None else _shekel(x), "source": s} for k, (x, s) in v.items()}
        return {
            "kind": kind,
            "label": "ויתור על הרכב" if not is_car else f'{car["name"]} ({car["registrationYear"]})',
            "reason": self._reason(reason_code, res.details, emp),
            "values": values,
        }

    def _pending_side(self, choice, car, car_sources: dict) -> dict:
        p = self.pending_text
        values = {k: {"value": p, "source": self.src["rep"]} for k in
                  ("participation", "car_cost", "family_share", "tax", "social", "net")}
        values["value_of_use"] = {"value": _shekel(car["valueOfUse"]), "source": car_sources["value_of_use"]}
        electric = car["drive"] == self.data.excel_values["electricDrive"]
        values["electric_refund_net"] = {
            "value": self.data.rules["electric"]["netBonus"] if electric else 0, "source": self.src["rules"]}
        return {"kind": choice.kind, "label": f'{car["name"]} ({car["registrationYear"]})',
                "reason": p, "values": values}

    def _card(self, args, emp_sources, today, alt, diff) -> dict:
        your_data = {f: {"value": args[f], "source": emp_sources.get(f, self.src["employee"])}
                     for f in EMPLOYEE_FIELDS if f in args}
        your_data["current"] = {"value": today["label"], "source": self.src["employee"]}
        if diff is None:
            second = self.pending_text
        elif diff["net"] == 0:
            second = "הנטו המשוער לא משתנה."
        else:
            direction = "עולה" if diff["net"] > 0 else "יורד"
            second = f'הנטו המשוער {direction} ב-{abs(diff["net"]):,} ₪ בחודש.'
        return {"your_data": your_data, "today": today, "alternative": alt, "diff": diff or {},
                "explanation": [alt["reason"], second]}

    # --------------------------------------------------------- tool: ask_rep

    def ask_rep(self, fields: list[str], question: str, car: Optional[str] = None,
                registration_year: Optional[int] = None, thread_id: str = "default") -> dict:
        salary = [f for f in fields if f in EMPLOYEE_FIELDS and f != "group"]
        if salary:  # an anonymous employee's data: the rep cannot know it
            return {"status": "not_for_rep", "fields": salary,
                    "instruction": "הנציג לא יודע את נתוני השכר של העובד. שאל את העובד, "
                                   "ואמור לו שהנתונים מופיעים בתלוש השכר שלו."}
        car_key = None
        if car:
            kind, found = self._resolve_car(car, registration_year)
            car_key = self._car_key(kind, found) if kind in ("catalog", "tax") else car.strip().upper()
        req = self.queue.add(thread_id, fields, question, car_key)
        return {"status": "sent", "request_id": req["id"], "fields": req["fields"],
                "message_to_employee": self.cfg["texts"]["repSent"]}
