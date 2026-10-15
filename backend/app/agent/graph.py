"""The agent: LangGraph's prebuilt ReAct agent with 4 tools.

The model decides what to ask and which tool to call. The guards are inside the
tools (app/agent/advisor.py). The model never sees the conversation id or the
history parameters - they are injected.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import InjectedState, create_react_agent

from app.agent.advisor import Advisor
from app.agent.prompt import build_prompt
from app.timing import timed

TOOL_NAMES = {"lookup_vehicle", "check_eligibility", "calculate", "ask_rep"}

Kind = Literal["car", "family_car", "waiver"]


def _thread(config: RunnableConfig) -> str:
    return (config or {}).get("configurable", {}).get("thread_id", "default")


def _dump(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)


def make_tools(data, rep_queue, cfg: dict) -> list:
    advisor = Advisor(data, rep_queue, cfg)

    @tool
    def lookup_vehicle(
        name: Annotated[str, "שם מסחרי של הרכב בלבד, למשל ATTO 2 או MODEL 3"],
        state: Annotated[dict, InjectedState],
        registration_year: Annotated[Optional[int], "שנת רישום, אם ידועה"] = None,
        model_code: Annotated[Optional[str], "קוד דגם מתוך candidates, אם נשאלה גרסה"] = None,
    ) -> str:
        """זיהוי רכב ושווי השימוש שלו: קודם בקטלוג של שטראוס, ואחר כך בקובץ רשות המסים."""
        with timed("tool lookup_vehicle"):
            return _dump(advisor.lookup_vehicle(name, registration_year, model_code, history=state["messages"]))

    @tool
    def check_eligibility(
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        occupation: Annotated[Optional[str], "עיסוק, שם מדויק מהרשימה"] = None,
        group: Annotated[Optional[str], "קבוצת הזכאות שהעובד ציין: א/ב/ג/ד"] = None,
        alternative_kind: Annotated[Optional[Kind], "car / family_car / waiver"] = None,
        alternative_car: Annotated[Optional[str], "שם הרכב בחלופה"] = None,
        alternative_car_year: Annotated[Optional[int], "שנת רישום, לרכב שלא בקטלוג"] = None,
        children: Annotated[Optional[int], "ילדים עד גיל 23, רק למסלול המשפחתי"] = None,
    ) -> str:
        """האם העובד זכאי לחלופה, ולמה."""
        args = dict(occupation=occupation, group=group, alternative_kind=alternative_kind,
                    alternative_car=alternative_car, alternative_car_year=alternative_car_year,
                    children=children)
        with timed("tool check_eligibility"):
            return _dump(advisor.check_eligibility(args, history=state["messages"], thread_id=_thread(config)))

    @tool
    def calculate(
        state: Annotated[dict, InjectedState],
        config: RunnableConfig,
        occupation: Annotated[Optional[str], "עיסוק, שם מדויק מהרשימה"] = None,
        group: Annotated[Optional[str], "קבוצת הזכאות שהעובד ציין: א/ב/ג/ד"] = None,
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
        with timed("tool calculate"):
            return _dump(advisor.calculate(args, history=state["messages"], thread_id=_thread(config)))

    @tool
    def ask_rep(
        fields: Annotated[list[str], "השדות שחסרים, כפי שהופיעו ב-fields של הכלי"],
        question: Annotated[str, "השאלה לנציג, משפט אחד"],
        config: RunnableConfig,
        car: Annotated[Optional[str], "שם הרכב, אם השאלה על רכב"] = None,
        registration_year: Annotated[Optional[int], "שנת רישום של הרכב"] = None,
    ) -> str:
        """שולח שאלה לנציג התחבורה. הנציג לא מדבר עם העובד - רק עונה על השאלה."""
        with timed("tool ask_rep"):
            return _dump(advisor.ask_rep(fields, question, car, registration_year, thread_id=_thread(config)))

    tools = [lookup_vehicle, check_eligibility, calculate, ask_rep]
    assert {t.name for t in tools} == TOOL_NAMES
    return tools


def build_agent(model, data, rep_queue, cfg: dict, checkpointer=None):
    return create_react_agent(
        model,
        make_tools(data, rep_queue, cfg),
        prompt=build_prompt(data, cfg),
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )
