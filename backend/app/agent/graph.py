"""The agent: LangGraph's prebuilt ReAct agent with 6 tools.

The model decides what to ask and which tool to call. The guards are inside the
tools (app/agent/advisor.py). The model never sees the conversation id, the employee id or the
history parameters - they are injected. The employee's profile (app/profile.py) is filled in by the
tools, in code; the prompt names only which of its fields are there.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Optional

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import InjectedState, create_react_agent

from app.agent.advisor import Advisor
from app.agent.car_options import CarOptions
from app.agent.prompt import address_section, build_prompt, profile_section, tone_section
from app.data.specs_store import load_specs_config, snapshot_store
from app.timing import timed

BACKEND_DIR = Path(__file__).resolve().parents[2]

TOOL_NAMES = {"lookup_vehicle", "check_eligibility", "calculate", "ask_rep", "car_specs", "rank_options"}

Kind = Literal["car", "family_car", "waiver"]
Drive = Literal["electric", "plug_in", "hybrid", "petrol", "diesel"]
SortBy = Literal["net", "safety", "seats", "power", "consumption", "pollution"]
FILTERS = ("drive", "min_seats", "body_type", "automatic", "adaptive_cruise", "reverse_camera", "min_horsepower",
           "min_safety_score", "min_safety_level", "max_pollution_group", "max_participation")


def _thread(config: RunnableConfig) -> str:
    return (config or {}).get("configurable", {}).get("thread_id", "default")


def _employee(config: RunnableConfig) -> Optional[str]:
    """The logged-in employee (app/api/common.thread_config); None in the console and most tests."""
    return (config or {}).get("configurable", {}).get("employee_id")


def _dump(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)


def make_tools(data, rep_queue, cfg: dict, specs=None, profiles=None) -> list:
    """specs: the car specs store; None = the snapshot in git (tests, evals, the console chat).
    profiles: the employees' profiles; None = none."""
    advisor = Advisor(data, rep_queue, cfg, profiles=profiles)
    options = CarOptions(advisor, specs if specs is not None else snapshot_store(BACKEND_DIR),
                         load_specs_config(BACKEND_DIR))

    @tool
    def lookup_vehicle(
        name: Annotated[str, "שם מסחרי של הרכב בלבד, למשל ATTO 2 או MODEL 3"],
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        registration_year: Annotated[Optional[int], "שנת רישום, אם ידועה"] = None,
        model_code: Annotated[Optional[str], "קוד דגם מתוך candidates, אם נשאלה גרסה"] = None,
        alternative: Annotated[bool, "true אם זה רכב שהעובד רוצה לעבור אליו (לא הרכב של היום)"] = False,
    ) -> str:
        """זיהוי רכב. הרכב של היום: קודם בקטלוג של שטראוס, ואחר כך בקובץ רשות המסים.
        רכב לעבור אליו (alternative=true): רק מהקטלוג, עם ההשתתפות שבקטלוג."""
        with timed("tool lookup_vehicle"):
            return _dump(advisor.lookup_vehicle(name, registration_year, model_code, history=state["messages"],
                                                alternative=alternative, employee_id=_employee(config),
                                                thread_id=_thread(config)))

    @tool
    def check_eligibility(
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        occupation: Annotated[Optional[str], "עיסוק, שם מדויק מהרשימה"] = None,
        employee_stated_group: Annotated[Optional[str], "רק אם העובד עצמו טוען לקבוצה (א/ב/ג/ד). הקבוצה עצמה נלקחת מהעיסוק, בקוד"] = None,
        alternative_kind: Annotated[Optional[Kind], "car / family_car / waiver"] = None,
        alternative_car: Annotated[Optional[str], "שם הרכב בחלופה"] = None,
        alternative_car_year: Annotated[Optional[int], "שנת רישום, לרכב שלא בקטלוג"] = None,
        children: Annotated[Optional[int], "ילדים עד גיל 23, רק למסלול המשפחתי"] = None,
    ) -> str:
        """האם העובד זכאי לחלופה, ולמה."""
        args = dict(occupation=occupation, group=employee_stated_group, alternative_kind=alternative_kind,
                    alternative_car=alternative_car, alternative_car_year=alternative_car_year,
                    children=children)
        with timed("tool check_eligibility"):
            return _dump(advisor.check_eligibility(args, history=state["messages"], thread_id=_thread(config),
                                                   employee_id=_employee(config)))

    @tool
    def calculate(
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        occupation: Annotated[Optional[str], "עיסוק, שם מדויק מהרשימה"] = None,
        employee_stated_group: Annotated[Optional[str], "רק אם העובד עצמו טוען לקבוצה (א/ב/ג/ד). הקבוצה עצמה נלקחת מהעיסוק, בקוד"] = None,
        base: Annotated[Optional[float], "שכר בסיס חודשי ברוטו"] = None,
        commission: Annotated[Optional[float], "עמלות חודשיות (0 אם אין)"] = None,
        bonus: Annotated[Optional[float], "בונוס חודשי (0 אם אין)"] = None,
        pension_pct: Annotated[Optional[float], "אחוז הפרשת עובד לפנסיה"] = None,
        keren_pct: Annotated[Optional[float], "אחוז הפרשת עובד לקרן השתלמות (0 אם אין)"] = None,
        credit_points: Annotated[Optional[float], "נקודות זיכוי"] = None,
        current_kind: Annotated[Optional[Literal["car", "waiver"]], "היום: car או waiver (אחזקה)"] = None,
        current_car: Annotated[Optional[str], "שם הרכב של היום"] = None,
        current_car_year: Annotated[Optional[int], "שנת רישום של רכב היום, אם לא בקטלוג"] = None,
        current_participation: Annotated[Optional[float], "השתתפות חודשית שהעובד משלם היום"] = None,
        alternative_kind: Annotated[Optional[Kind], "החלופה: car / family_car / waiver"] = None,
        alternative_car: Annotated[Optional[str], "שם הרכב בחלופה"] = None,
        alternative_car_year: Annotated[Optional[int], "שנת רישום, לרכב שלא בקטלוג"] = None,
        children: Annotated[Optional[int], "ילדים עד גיל 23, רק למסלול המשפחתי"] = None,
    ) -> str:
        """נטו היום מול נטו בחלופה, עם הפרש מוכן לכל רכיב וכרטיס השוואה. כל המספרים מחושבים בקוד."""
        args = {k: v for k, v in locals().items() if k in Advisor.CALCULATE_FIELDS}
        args["group"] = employee_stated_group  # inside the code it is "group": the contradiction check
        with timed("tool calculate"):
            return _dump(advisor.calculate(args, history=state["messages"], thread_id=_thread(config),
                                           employee_id=_employee(config)))

    @tool
    def ask_rep(
        fields: Annotated[list[str], "השדות שחסרים, כפי שהופיעו ב-fields של הכלי"],
        question: Annotated[str, "השאלה לנציג, משפט אחד"],
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        car: Annotated[Optional[str], "שם הרכב, אם השאלה על רכב"] = None,
        registration_year: Annotated[Optional[int], "שנת רישום של הרכב"] = None,
        about: Annotated[Optional[Literal["current", "alternative"]],
                         "על איזה רכב השאלה: current (הרכב של היום) או alternative (רכב לעבור אליו)"] = None,
        confirm: Annotated[bool, "true כשהעובד רק מבקש לוודא שסכום ההשתתפות מהקטלוג הוא שלו, "
                                 "בלי לטעון שיש לו הסדר אחר"] = False,
    ) -> str:
        """שולח שאלה לנציג התחבורה. הנציג לא מדבר עם העובד - רק עונה על השאלה."""
        with timed("tool ask_rep"):
            return _dump(advisor.ask_rep(fields, question, car, registration_year, thread_id=_thread(config),
                                         about=about, confirm=confirm, history=state["messages"]))

    @tool(response_format="content_and_artifact")
    def car_specs(car: Annotated[str, "שם הרכב בקטלוג, באנגלית כמו ברשימה (למשל BYD DOLPHIN)"]
                  ) -> tuple[str, Optional[dict]]:
        """מה ידוע על רכב מהקטלוג: המפרט הרשמי (משרד התחבורה, EEA), עם מקור ושנה לכל נתון, וקישור ליבואן."""
        with timed("tool car_specs"):
            result = options.car_specs(car)
        # the model reads the specs to answer; the same specs also go to the screen as a card
        return _dump(result), options.specs_card(result)

    @tool(response_format="content_and_artifact")
    def rank_options(
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        occupation: Annotated[Optional[str], "עיסוק, שם מדויק מהרשימה"] = None,
        employee_stated_group: Annotated[Optional[str], "רק אם העובד עצמו טוען לקבוצה (א/ב/ג/ד). הקבוצה עצמה נלקחת מהעיסוק, בקוד"] = None,
        base: Annotated[Optional[float], "שכר בסיס חודשי ברוטו"] = None,
        commission: Annotated[Optional[float], "עמלות חודשיות (0 אם אין)"] = None,
        bonus: Annotated[Optional[float], "בונוס חודשי (0 אם אין)"] = None,
        pension_pct: Annotated[Optional[float], "אחוז הפרשת עובד לפנסיה"] = None,
        keren_pct: Annotated[Optional[float], "אחוז הפרשת עובד לקרן השתלמות (0 אם אין)"] = None,
        credit_points: Annotated[Optional[float], "נקודות זיכוי"] = None,
        current_kind: Annotated[Optional[Literal["car", "waiver"]], "היום: car או waiver (אחזקה)"] = None,
        current_car: Annotated[Optional[str], "שם הרכב של היום"] = None,
        current_car_year: Annotated[Optional[int], "שנת רישום של רכב היום, אם לא בקטלוג"] = None,
        current_participation: Annotated[Optional[float], "השתתפות חודשית שהעובד משלם היום"] = None,
        children: Annotated[Optional[int], "ילדים עד גיל 23 (למסלול המשפחתי)"] = None,
        sort_by: Annotated[Optional[SortBy], "לפי מה לסדר. ברירת מחדל: net (הכי הרבה נטו)"] = None,
        drive: Annotated[Optional[list[Drive]], "סינון: סוגי הנעה"] = None,
        min_seats: Annotated[Optional[int], "סינון: מספר מושבים מינימלי"] = None,
        body_type: Annotated[Optional[list[str]], "סינון: סוג מרכב (הצ'בק, סדאן, פנאי-שטח, MPV)"] = None,
        automatic: Annotated[Optional[bool], "סינון: תיבה אוטומטית"] = None,
        adaptive_cruise: Annotated[Optional[bool], "סינון: בקרת שיוט אדפטיבית"] = None,
        reverse_camera: Annotated[Optional[bool], "סינון: מצלמת רוורס"] = None,
        min_horsepower: Annotated[Optional[int], "סינון: כוח סוס מינימלי"] = None,
        min_safety_score: Annotated[Optional[float], "סינון: ניקוד בטיחות מינימלי"] = None,
        min_safety_level: Annotated[Optional[int], "סינון: רמת אבזור בטיחותי מינימלית"] = None,
        max_pollution_group: Annotated[Optional[int], "סינון: קבוצת זיהום מקסימלית (1 הכי נקי)"] = None,
        max_participation: Annotated[Optional[float], "סינון: השתתפות חודשית מקסימלית"] = None,
    ) -> tuple[str, Optional[dict]]:
        """מסדר את הרכבים מהקטלוג שהעובד זכאי להם, לפי מה שחשוב לו, ומחשב נטו לכל אחד. מחזיר את 3 הראשונים."""
        local = locals()
        args = {k: local[k] for k in Advisor.CALCULATE_FIELDS if k in local and not k.startswith("alternative")}
        args["group"] = employee_stated_group
        filters = {k: local[k] for k in FILTERS}
        with timed("tool rank_options"):
            result, card = options.rank_options(args, filters, sort_by, history=state["messages"],
                                                thread_id=_thread(config), employee_id=_employee(config))
        # the model reads the short result; the card (full specs) goes to the screen as the artifact
        return _dump(result), card

    tools = [lookup_vehicle, check_eligibility, calculate, ask_rep, car_specs, rank_options]
    assert {t.name for t in tools} == TOOL_NAMES
    return tools


def build_agent(model, data, rep_queue, cfg: dict, checkpointer=None, specs=None, profiles=None, employees=None):
    """profiles: the employees' profiles (app/profile.py). With them, the prompt of a logged-in
    employee's run ends with which profile fields are there - their names, never their values - and the
    style block of the tone they chose. Read at every model call: a new setting applies from the next message.
    employees: whether the employee has a name (app/employees.py) - only the placeholder goes in the prompt."""
    base = build_prompt(data, cfg)
    prompt = base
    if profiles is not None:
        def prompt(state, config: RunnableConfig):
            employee = _employee(config)
            text = base
            if employee:
                text += "\n\n" + profile_section(profiles.get(employee), cfg, data.occupations)
                has_name = bool(employees is not None and (employees.name(employee) or "").strip())
                text += "\n\n" + address_section(profiles.settings(employee).get("address"), has_name, cfg)
                tone = tone_section(profiles.settings(employee).get("tone"), cfg)
                if tone:
                    text += "\n\n" + tone
            return [SystemMessage(content=text)] + state["messages"]

    return create_react_agent(
        model,
        make_tools(data, rep_queue, cfg, specs, profiles),
        prompt=prompt,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )
