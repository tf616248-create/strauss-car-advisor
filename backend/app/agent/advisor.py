"""The guards behind the agent's 4 tools. No LLM here - plain functions over the data.

Every method returns a dict with a `status`:
  ok | missing | invalid | contradiction | not_eligible | ambiguous | not_found
  | needs_rep | waiting_rep | sent | not_for_rep | not_in_catalog | did_you_mean
Only `ok` (and the known half of `waiting_rep` and `needs_rep`: today) carries calculated numbers.

A car to move to comes only from the catalog (not_in_catalog, did_you_mean); its participation is the catalog's,
and the rep's only when the catalog has none or the employee has a personal arrangement. Today's car: the
catalog, then the Tax Authority file; its participation is the employee's, never the catalog's.

When to ask the rep is decided here; the thresholds live in config/agent.json.
Attempts are counted from the conversation history (earlier tool results), so the
tools stay stateless.
"""
from __future__ import annotations

import difflib
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


def _norm(name: str) -> str:
    """A car name without spaces or signs: "atto3" and "KONA-EV" read like "ATTO 3" and "KONA EV"."""
    return re.sub(r"[^0-9A-Z]", "", name.upper())


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
            self.profiles.update(employee_id, values, source="chat")
        except Exception:  # noqa: BLE001 - the answer matters more than the profile
            log.exception("could not update the profile of %s", employee_id)
            return
        profile_mod.trace_profile("profile_updated", sorted(values))
        updated.extend(f for f in values if f not in updated)

    def _with_profile(self, res: dict, updated: list, info: Optional[dict] = None) -> dict:
        """The tool's result, and what Kobi says when the profile changed ("עדכנתי בפרופיל"); info: the occupation
        the model passed, recognized (and kept) or not_found with close ones."""
        if info:
            res.update(info)
        if updated:
            t = self.cfg["texts"]["profile"]
            res["profile_updated"] = list(updated)
            res["message_profile"] = t["updated"].format(fields=", ".join(t["labels"][f] for f in updated))
        return res

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

    # A car the employee wants to move to: only from the catalog. Today's car goes through _resolve_car (the
    # catalog, then the Tax Authority file), as before.

    def _resolve_alternative(self, name: str):
        """('catalog', car) | ('did_you_mean', [catalog names]) | ('not_in_catalog', {"electric": bool}).

        In the catalog = the catalog's name, and when the Tax Authority file has a car with exactly the name asked
        for, the same manufacturer and model codes: "BYD SEAL U" holds "SEAL" but is another car, and "TANG" has
        ATTO 3's codes under another name. A name found nowhere and close to a catalog car: did_you_mean."""
        car = self.data.find_car(name)
        if car:
            return "catalog", car
        q = f" {name.strip().upper()} "
        contained = sorted((c for c in self.data.catalog.values() if f" {c['name'].upper()} " in q),
                           key=lambda c: len(c["name"]), reverse=True)  # "TOYOTA COROLLA CROSS": not COROLLA
        if contained:
            c = contained[0]
            exact = [h for h in self.data.vehicles.search_name(name) if _norm(h["name"]) == _norm(name)]
            if not exact or any((h["manufacturerCode"], h["modelCode"]) == (c["manufacturerCode"], c["modelCode"])
                                for h in exact):
                return "catalog", c
        hits = self.data.vehicles.search_name(name)
        rest = name.split(None, 1)[1] if len(name.split()) > 1 else ""
        if not hits and re.search(r"[A-Za-z]{3}", rest):  # "PORSCHE TAYCAN": the file has "TAYCAN 4S" (not "3")
            hits = self.data.vehicles.search_name(rest)
        if not hits:
            close = self._close_names(name)
            if close:
                return "did_you_mean", close
        electric = self.data.excel_values["electricDrive"]
        return "not_in_catalog", {"electric": bool(hits) and all(h["driveName"] == electric for h in hits)}

    def _close_names(self, name: str) -> list[str]:
        """Catalog cars a name not found anywhere may mean: the same letters ("atto3", "KONA-EV"), or a typo."""
        q = _norm(name)
        names = {_norm(c["name"]): c["name"] for c in self.data.catalog.values()}
        same = [n for k, n in names.items() if k == q or (len(k) >= 3 and k in q)]
        if same:
            return same
        return [names[k] for k in difflib.get_close_matches(q, list(names), n=3, cutoff=0.8)]

    def _group_of(self, args: dict, employee_id: Optional[str]) -> Optional[str]:
        """The employee's group from the occupation (passed, or in the profile); None when unknown."""
        occupation = args.get("occupation") or self._profile(employee_id).get("occupation")
        if not occupation:
            return None
        found = self.matcher.find(occupation)
        return self.data.occupations[found["occupation"]]["group"] if found["status"] == "ok" else None

    def _options(self, group: Optional[str], electric_first: bool) -> list[dict]:
        """The catalog cars the employee may take instead (their group or lower, not the family track)."""
        if group is None:
            return []
        rules, electric = self.data.rules, self.data.excel_values["electricDrive"]
        order = rules["groupOrder"]
        cars = [c for c in self.data.catalog.values()
                if c["id"] not in rules["familyTrack"]["cars"] and c["group"] in order
                and order.index(c["group"]) <= order.index(group)]
        if electric_first:
            cars.sort(key=lambda c: c["drive"] != electric)  # stable: the catalog's order otherwise
        return [{"name": c["name"], "drive": c["drive"], "group": c["group"]} for c in cars]

    def _alternative_problem(self, kind: str, found, name: str, group: Optional[str]) -> Optional[dict]:
        if kind == "did_you_mean":
            return {"status": "did_you_mean", "car": name, "suggestions": found,
                    "instruction": "השם לא כתוב כמו ברשימת רכבי החברה. שאל את העובד אם התכוון לרכב מ-suggestions, "
                                   "ואל תחשב לפני שהוא עונה."}
        if kind == "not_in_catalog":
            res = {"status": "not_in_catalog", "car": name,
                   "message_to_employee": self.cfg["texts"]["notInCatalog"]["message"],
                   "options": self._options(group, found["electric"]), "electric_first": found["electric"],
                   "instruction": "הרכב לא ברשימת רכבי החברה. כתוב לעובד את message_to_employee, והצע לו את "
                                  "הרכבים שב-options (אם electric_first, החשמליים ראשונים), ושאל אם לחשב אחד מהם. "
                                  "אל תחשב שווי שימוש או נטו לרכב הזה, ואל תשלח לנציג."}
            if group is None:
                res["instruction"] += (" אין עדיין עיסוק, ולכן אין רשימה: שאל את העובד מה העיסוק שלו (occupation), "
                                       "ואז קרא שוב.")
            return res
        return None

    def _check_alternative(self, args: dict, employee_id: Optional[str]) -> Optional[dict]:
        """Before anything else: an alternative outside the catalog has nothing to calculate."""
        if args.get("alternative_kind") not in ("car", "family_car") or not args.get("alternative_car"):
            return None
        kind, found = self._resolve_alternative(args["alternative_car"])
        if kind == "catalog":
            return None
        return self._alternative_problem(kind, found, args["alternative_car"], self._group_of(args, employee_id))

    # ---------------------------------------------------------- tool: lookup

    def lookup_vehicle(self, name: str, registration_year: Optional[int] = None,
                       model_code: Optional[str] = None, history: Iterable = (), alternative: bool = False,
                       employee_id: Optional[str] = None) -> dict:
        """alternative: a car the employee wants to move to - only from the catalog."""
        if alternative:
            kind, found = self._resolve_alternative(name)
            if kind != "catalog":
                return self._alternative_problem(kind, found, name, self._group_of({}, employee_id))
        else:
            kind, found = self._resolve_car(name, registration_year, model_code)
        if kind == "catalog":
            car = {"name": found["name"], "registrationYear": found["registrationYear"],
                   "valueOfUse": found["valueOfUse"], "drive": found["drive"], "group": found["group"],
                   "companyCost": found["companyCost"], "defaultParticipation": found["defaultParticipation"],
                   "inCatalog": True, "source": self.src["catalog"]}
            if alternative and found["defaultParticipation"] is not None:
                car["participation"] = found["defaultParticipation"]
                car["participation_note"] = self._catalog_note(employee_id, found["defaultParticipation"])
            return {"status": "ok", "car": car}
        if kind == "tax":
            return {
                "status": "ok",
                "car": {"name": found["name"], "registrationYear": found["registrationYear"],
                        "modelCode": found["modelCode"], "valueOfUse": found["valueOfUse"],
                        "drive": found["drive"], "inCatalog": False, "source": self.src["taxAuthority"]},
                "instruction": "הרכב לא בקטלוג. אם זה הרכב של היום: שווי השימוש מרשות המסים, והמשך כרגיל. "
                               "אם זה רכב שהעובד רוצה לעבור אליו: קרא שוב עם alternative=true.",
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
                        employee_id: Optional[str] = None, updated: Optional[list] = None,
                        info: Optional[dict] = None):
        """Apply rep answers, the profile and the payslip, then validate. Returns (problem | None, args, sources).
        updated: gets the profile fields this call changed (a new value the employee wrote)."""
        updated = updated if updated is not None else []
        info = info if info is not None else {}
        answers = self.queue.answers(thread_id)
        pending = self.queue.pending_fields(thread_id)
        args = {k: v for k, v in args.items() if v not in (None, "")}
        if "occupation" in args:  # written in the chat: recognized (then kept in the profile), or not_found
            found = self.matcher.find(args["occupation"])  # as the employee wrote it: "מנהלת אזור המכירות"
            if found["status"] == "ok":
                args["occupation"] = found["occupation"]
                info["occupation"] = {"status": "recognized", "occupation": found["occupation"]}
            else:
                info["occupation"] = {"status": "not_found", "suggestions": found["suggestions"]}
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
        # the group comes from the occupation (the sheet), in code - never from the model. "group" in args is only
        # what the employee stated (employee_stated_group): checked against it below (contradiction, rep)
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
            if "occupation" in bad:
                res["instruction"] += (" העיסוק לא נמצא בטבלת העיסוקים: שאל את העובד מה העיסוק שלו, והצע לו את "
                                       "occupation.suggestions. אל תנחש עיסוק או קבוצה.")
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
        if prefix == "alternative":  # only from the catalog (_check_alternative ran first)
            found_kind, car = self._resolve_alternative(name)
            if found_kind != "catalog":
                return self._alternative_problem(found_kind, car, name, args.get("group")), None, None, {}, []
        else:
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
            # The catalog's participation. The rep's, only when the catalog has none, or the employee has a
            # personal arrangement (then a question about it is pending or answered for this car). A question
            # that only asks to confirm the catalog's amount: meanwhile calculated by it, marked "awaiting".
            answers = self.queue.answers(thread_id)
            pending = self.queue.pending_fields(thread_id)
            confirming = {("participation", r["car_key"]) for r in self.queue.pending(thread_id)
                          if r.get("confirm") and "participation" in r["fields"]}
            car = dict(car)
            car_sources["participation"] = self.src["catalog"]
            if ("participation", key) in answers:
                car["defaultParticipation"] = answers[("participation", key)]
                car_sources["participation"] = self.src["rep"]
            elif ("participation", key) in confirming and car.get("defaultParticipation") is not None:
                car_sources["awaiting"] = ["participation"]
            elif ("participation", key) in pending:
                pending_keys.append("participation")
            elif car.get("defaultParticipation") is None:
                return ({"status": "needs_rep", "fields": ["participation"],
                         "car": car["name"], "registration_year": car["registrationYear"],
                         "instruction": "לרכב הזה אין סכום השתתפות בקטלוג. קרא ל-ask_rep עם השדה והרכב האלה, "
                                        "about=alternative. אל תשאל את העובד. בינתיים הצג את מצב היום מהכרטיס."},
                        None, car, car_sources, [])
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
        updated, info = [], {}
        return self._with_profile(self._check_eligibility(args, history, thread_id, employee_id, updated, info),
                                  updated, info)

    def _check_eligibility(self, args, history, thread_id, employee_id, updated, info) -> dict:
        args = {k: args.get(k) for k in self.ELIGIBILITY_FIELDS}
        problem = self._check_alternative(args, employee_id)
        if problem:
            return problem
        problem, args, _ = self._check_employee(args, history, thread_id, False, employee_id, updated, info)
        if problem:
            return problem
        problem, choice, _, _, _ = self._resolve_choice(args, "alternative", thread_id)
        if problem:
            return problem
        emp = self._employee_input(args)
        res = build_scenario(emp, choice, self.data)
        return {"status": "ok", "eligible": res.eligible, "reason_code": res.reason_code,
                "reason": self._reason(res.reason_code, res.details, emp)}

    # ------------------------------------------------------- tool: calculate

    def calculate(self, args: dict, history: Iterable = (), thread_id: str = "default",
                  employee_id: Optional[str] = None) -> dict:
        """employee_id: whose profile fills in what the model did not pass (None: no profile)."""
        updated, info = [], {}
        return self._with_profile(self._calculate(args, history, thread_id, employee_id, updated, info), updated, info)

    def _calculate(self, args, history, thread_id, employee_id, updated, info) -> dict:
        args = {k: args.get(k) for k in self.CALCULATE_FIELDS}
        problem = self._check_alternative(args, employee_id)  # outside the catalog: say so before any question
        if problem:
            return problem
        problem, args, emp_sources = self._check_employee(args, history, thread_id, True, employee_id, updated, info)
        if problem:
            return problem
        problem, today_choice, today_car, today_src, _ = self._resolve_choice(args, "current", thread_id)
        if problem:
            return problem
        emp = self._employee_input(args)
        today_res = build_scenario(emp, today_choice, self.data, is_current=True)
        today = self._side(emp, today_res, today_car, today_src, "today", args["current_kind"])

        problem, alt_choice, alt_car, alt_src, pending = self._resolve_choice(args, "alternative", thread_id)
        if problem:
            if problem["status"] == "needs_rep":  # meanwhile: today, and the alternative waiting for the rep
                alt_side = self._pending_side(args["alternative_kind"], alt_car, alt_src)
                problem["card"] = self._card(args, emp_sources, today, alt_side, None)
            return problem

        if pending:
            alt_side = self._pending_side(alt_choice.kind, alt_car, alt_src)
            return {"status": "waiting_rep", "fields": pending,
                    "card": self._card(args, emp_sources, today, alt_side, None),
                    "instruction": "חלק מהנתונים ממתינים לנציג. הצג את מה שידוע, ואמור שהחלופה תתעדכן."}

        alt_res = build_scenario(emp, alt_choice, self.data)
        if not alt_res.eligible:
            return {"status": "not_eligible", "reason_code": alt_res.reason_code,
                    "reason": self._reason(alt_res.reason_code, alt_res.details, emp)}
        alt = self._side(emp, alt_res, alt_car, alt_src, alt_res.reason_code, args["alternative_kind"])
        diff = {k: alt["values"][k]["value"] - today["values"][k]["value"] for k in DIFF_KEYS}
        res = {"status": "ok", "card": self._card(args, emp_sources, today, alt, diff)}
        if alt_src.get("awaiting"):  # the rep is asked to confirm the catalog's amount: calculated by it meanwhile
            awaiting = self.cfg["texts"]["awaitingConfirmation"]
            res["awaiting_confirmation"] = alt_src["awaiting"]
            res["card"]["awaiting_confirmation"] = {"fields": alt_src["awaiting"], "label": awaiting["label"],
                                                    "note": awaiting["note"]}
            res["instruction"] = ("החישוב לפי סכום ההשתתפות שבקטלוג, וממתין לאישור הנציג. "
                                  "כתוב זאת לעובד: החלופה תתעדכן כשהנציג יענה.")
        elif alt_car is not None and alt_src.get("participation") == self.src["catalog"]:
            res["participation_note"] = self._catalog_note(employee_id, alt["values"]["participation"]["value"])
        return res

    def _catalog_note(self, employee_id: Optional[str], amount) -> str:
        """Where the participation comes from, and an invitation to correct it - in the employee's form of address
        (plural until chosen, and without a profile)."""
        address = self.cfg["settings"]["defaults"]["address"]
        if self.profiles is not None and employee_id:
            address = self.profiles.settings(employee_id).get("address") or address
        return self.cfg["texts"]["catalogParticipation"][address].format(amount=f"{amount:,}")

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

    def _pending_side(self, kind: str, car, car_sources: dict) -> dict:
        p = self.pending_text
        values = {k: {"value": p, "source": self.src["rep"]} for k in
                  ("participation", "car_cost", "family_share", "tax", "social", "net")}
        values["value_of_use"] = {"value": _shekel(car["valueOfUse"]), "source": car_sources["value_of_use"]}
        if car.get("companyCost") is not None:  # a catalog car: its cost is known
            values["car_cost"] = {"value": _shekel(car["companyCost"]), "source": car_sources["car_cost"]}
        electric = car["drive"] == self.data.excel_values["electricDrive"]
        values["electric_refund_net"] = {
            "value": self.data.rules["electric"]["netBonus"] if electric else 0, "source": self.src["rules"]}
        return {"kind": kind, "label": f'{car["name"]} ({car["registrationYear"]})',
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
                registration_year: Optional[int] = None, thread_id: str = "default",
                about: Optional[str] = None, confirm: bool = False) -> dict:
        """about: "current" (today's car) or "alternative" (a car to move to). A question about an alternative
        outside the catalog is refused; today's car (e.g. not found in the Tax Authority file) goes as before.
        confirm: the employee only asks to check the catalog's participation - meanwhile calculate uses it,
        marked awaiting confirmation (a personal arrangement, without confirm: nothing calculated meanwhile)."""
        salary = [f for f in fields if f in EMPLOYEE_FIELDS and f != "group"]
        if salary:  # an anonymous employee's data: the rep cannot know it
            return {"status": "not_for_rep", "fields": salary,
                    "instruction": "הנציג לא יודע את נתוני השכר של העובד. שאל את העובד, "
                                   "ואמור לו שהנתונים מופיעים בתלוש השכר שלו."}
        # the company's details of a car (group, cost, participation) are asked only about an alternative
        about_alternative = about == "alternative" or bool(set(fields) & set(COMPANY_FIELDS))
        if car and about_alternative and self._resolve_alternative(car)[0] != "catalog":
            return {"status": "not_in_catalog", "car": car,
                    "message_to_employee": self.cfg["texts"]["notInCatalog"]["message"],
                    "instruction": "לא שולחים לנציג שאלה על רכב חלופה שלא ברשימת רכבי החברה. "
                                   "קרא ל-calculate או ל-check_eligibility עם הרכב, כדי לקבל את הרכבים שהעובד זכאי להם."}
        car_key = None
        if car:
            kind, found = self._resolve_car(car, registration_year)
            car_key = self._car_key(kind, found) if kind in ("catalog", "tax") else car.strip().upper()
        req = self.queue.add(thread_id, fields, question, car_key, confirm=confirm)
        return {"status": "sent", "request_id": req["id"], "fields": req["fields"],
                "message_to_employee": self.cfg["texts"]["repSent"]}
