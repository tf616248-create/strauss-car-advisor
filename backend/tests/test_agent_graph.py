"""Wiring of the LangGraph agent, with a scripted fake model (no API calls)."""
import json
import re

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

from app.agent.advisor import load_agent_config
from app.agent.graph import TOOL_NAMES, build_agent
from app.agent.prompt import build_prompt
from app.agent.rep_queue import InMemoryRepQueue
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args


class ScriptedModel(GenericFakeChatModel):
    """Replays fixed AI messages; tool binding is a no-op. Streams text word by word,
    and a tool call as one chunk (the base fake can't stream tool calls)."""

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._generate(messages, stop, run_manager, **kwargs).generations[0].message
        if msg.tool_calls:
            chunks = [{"name": tc["name"], "args": json.dumps(tc["args"], ensure_ascii=False),
                       "id": tc["id"], "index": i} for i, tc in enumerate(msg.tool_calls)]
            yield ChatGenerationChunk(message=AIMessageChunk(content=msg.content, tool_call_chunks=chunks))
            return
        for part in re.split(r"(\s)", msg.content):
            if part:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))


def call(name, args, idx=0):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"{name}-{idx}"}])


def run(data, script, user_text="שאלה", thread="t"):
    queue = InMemoryRepQueue()
    agent = build_agent(ScriptedModel(messages=iter(script)), data, queue, load_agent_config(BACKEND_DIR))
    out = agent.invoke({"messages": [("user", user_text)]}, {"configurable": {"thread_id": thread}})
    return out, queue


def tool_results(out, name):
    return [json.loads(m.content) for m in out["messages"] if isinstance(m, ToolMessage) and m.name == name]


def test_seven_tools(data):
    assert TOOL_NAMES == {"lookup_vehicle", "check_eligibility", "calculate", "ask_rep", "car_specs", "rank_options",
                          "occupation_to_group"}


def test_car_specs_through_the_graph(data):
    script = [call("car_specs", {"car": "BYD DOLPHIN"}), AIMessage(content="סיום")]
    out, _ = run(data, script)
    [res] = tool_results(out, "car_specs")
    [msg] = [m for m in out["messages"] if isinstance(m, ToolMessage) and m.name == "car_specs"]
    assert msg.artifact["type"] == "specs" and msg.artifact["car"] == "BYD DOLPHIN"  # the card for the screen
    assert res["status"] == "ok"
    assert res["specs"]["electric_consumption"]["provisional"] is True


def test_rank_options_through_the_graph(data):
    args = {k: v for k, v in employee_args(data, "E-001").items() if not k.startswith("alternative")}
    script = [call("rank_options", {**args, "drive": ["electric"], "sort_by": "safety"}), AIMessage(content="סיום")]
    out, _ = run(data, script)
    [res] = tool_results(out, "rank_options")
    [msg] = [m for m in out["messages"] if isinstance(m, ToolMessage) and m.name == "rank_options"]
    assert "specs" not in msg.content  # the model reads the short result
    assert msg.artifact["type"] == "ranking" and msg.artifact["options"][0]["specs"]  # the card: full specs
    assert res["status"] == "ok"
    assert res["applied_filters"] == {"drive": ["electric"]}
    assert res["sort_by"] == "safety"
    assert len(res["options"]) <= 3


def test_calculate_through_the_graph(data):
    script = [call("calculate", employee_args(data, "E-001")), AIMessage(content="סיום")]
    out, _ = run(data, script)
    [res] = tool_results(out, "calculate")
    assert res["status"] == "ok"
    assert abs(res["card"]["diff"]["net"] - data.reference["E-001"]["diff"]) <= 1
    assert out["messages"][-1].content == "סיום"


def test_attempts_are_counted_from_conversation_history(data):
    script = [
        call("lookup_vehicle", {"name": "ZZZ"}, 0),
        call("lookup_vehicle", {"name": "ZZZ 2"}, 1),
        AIMessage(content="סיום"),
    ]
    out, _ = run(data, script)
    first, second = tool_results(out, "lookup_vehicle")
    assert first["status"] == "not_found"
    assert second["status"] == "needs_rep"


def test_ask_rep_uses_the_conversation_id(data):
    script = [
        call("ask_rep", {"fields": ["participation"], "question": "?", "car": "ATTO 2",
                         "registration_year": 2025}),
        AIMessage(content="סיום"),
    ]
    _, queue = run(data, script, thread="conv-42")
    assert len(queue.pending("conv-42")) == 1
    assert queue.pending("other") == []


def test_model_cannot_inject_conversation_state(data):
    """Injected parameters are hidden from the tool schema the model sees."""
    from app.agent.graph import make_tools

    for t in make_tools(data, InMemoryRepQueue(), load_agent_config(BACKEND_DIR)):
        props = t.tool_call_schema.model_json_schema().get("properties", {})
        assert "state" not in props and "config" not in props, t.name


# --- system prompt --------------------------------------------------------------


@pytest.fixture(scope="module")
def prompt(data):
    return build_prompt(data)


def test_prompt_core_rules(prompt):
    assert "החישוב תמיד בקוד, אף פעם לא במודל השפה." in prompt
    for phrase in ("מועתק כמו שהוא", "אסור לחשב", "לשנתי", "לאחוזים",
                   "פנה לנציג", "לספרות"):
        assert phrase in prompt, phrase


def test_prompt_lists_occupations(prompt, data):
    for occ in data.occupations:
        assert occ in prompt


def test_prompt_has_rep_message(prompt, data):
    assert load_agent_config(BACKEND_DIR)["texts"]["repSent"] in prompt


def test_prompt_lists_catalog_car_names(prompt, data):
    """Employees write 'קורולה קרוס'; the tools need the catalog name (COROLLA CROSS)."""
    for car in data.catalog.values():
        assert car["name"] in prompt


def test_prompt_rechecks_after_rep_answer(prompt):
    """After the rep answers, the model must call a tool again - not answer from memory."""
    note = load_agent_config(BACKEND_DIR)["texts"]["repAnswered"]
    assert note in prompt
    assert "אל תענה מהזיכרון" in prompt


def test_prompt_says_a_human_checks_the_numbers(prompt):
    assert "בן אדם יבדוק אחריך ידנית את התוצאות" in prompt
    assert "לא לשנות את המספרים שאתה מקבל מהכלים" in prompt


def explain_section(prompt):
    start = prompt.index("## שאלות הסבר")
    end = prompt.index("\n## ", start + 1)
    return prompt[start:end]


# one phrase per Strauss rule, written from strauss-rules.json (see CLAUDE.md)
STRAUSS_RULES = {
    "participation": "השתתפות עצמית יורדת מהנטו בלבד",  # participation.treatment = net_deduction
    "not_value_of_use": "לא מקטינה את שווי השימוש",  # participation.reducesValueOfUse = false
    "family": "הפער בין עלות הרכב לתקציב הקבוצה מתחלק",  # familyTrack.gapSplitEmployee
    "electric": "החברה מוסיפה סכום קבוע לנטו, ומגלמת אותו בברוטו",  # electric.method = gross_up
    "waiver": "מקבלים דמי אחזקה לפי העיסוק",  # waiver.allowedBy = occupation, maintenance per occupation
}


def test_prompt_explains_terms_without_numbers(prompt):
    """'What is value of use?' is answered from the prompt; a personal number goes to the tools."""
    section = explain_section(prompt)
    assert "בהסבר כללי אין מספרים" in section
    assert "כמה שווי השימוש שלי?" in section and "עוברת לכלים" in section
    assert "גוברים על כל ידע כללי" in section
    for name, phrase in STRAUSS_RULES.items():
        assert phrase in section, name
    assert not re.search(r"\d", section)  # no amounts: they live in strauss-rules.json


def test_prompt_asks_for_everything_missing_in_one_message(prompt):
    """Each question is another round trip: ask for all the missing data together."""
    assert "בהודעה אחת" in prompt


def test_prompt_does_not_send_employee_data_to_the_rep(prompt):
    assert "אחרי 2 ניסיונות כושלים" not in prompt
    assert "תלוש" in prompt


def test_prompt_sends_an_explicit_request_for_a_human_to_the_contact_button(prompt):
    """The rep only answers predefined fields; a person to write to is the contact button."""
    assert "מבקש במפורש לדבר עם אדם" in prompt
    assert '"שיחה עם נציג"' in prompt
    assert "אל תקרא ל-ask_rep בשביל זה" in prompt


def test_prompt_no_tables_in_the_chat(prompt):
    """The comparison is the card beside the chat; a table in the chat would repeat its numbers."""
    assert "בלי טבלאות" in prompt
    assert "בכרטיס" in prompt


def test_prompt_kobi_is_a_bot_and_says_so(prompt):
    assert "אתה כובי, בוט הרכב של שטראוס. אתה בוט, ואם שואלים – אומר זאת." in prompt
    assert "יועץ הרכב של שטראוס" not in prompt


def test_prompt_tone_section(prompt):
    """Like a friendly colleague: short opening, the point, one clear question; no flattery."""
    assert "## טון" in prompt
    assert "מדבר כמו עמית נחמד מהעבודה" in prompt
    assert "פונה בלשון שבה העובד כותב (זכר או נקבה). אם אין סימן, ברבים." in prompt
    assert "בלי חנופה" in prompt and "בלי אימוג'י" in prompt
    assert "אורך: 2–5 משפטים, אלא כשמציגים תוצאת חישוב." in prompt
    assert "הטון: חם וענייני" not in prompt
    assert "קצר וברור" not in prompt


def test_statuses_and_errors_speak_as_kobi():
    texts = load_agent_config(BACKEND_DIR)["texts"]
    assert texts["steps"] == {
        "lookup_vehicle": "כובי מחפש את הרכב…",
        "check_eligibility": "כובי בודק זכאות…",
        "calculate": "כובי מחשב נטו…",
        "ask_rep": "כובי שלח שאלה לנציג התחבורה ⏳",
        "payslip": "כובי קורא את התלוש…",
        "occupation_to_group": "כובי בודק את העיסוק…",
    }
    assert texts["overloaded"] == "כובי עמוס כרגע. נסו שוב בעוד רגע."


# --- recommending: only through rank_options --------------------------------------


def test_prompt_recommends_only_through_rank_options(prompt):
    assert ("מותר להמליץ רק דרך rank_options, ולפי מה שהעובד אמר שחשוב לו. בלי rank_options, לא מציגים רכבים. "
            "מנסחים 'סידרתי לפי הנתונים', לא 'שטראוס ממליצה' ולא 'הכי טוב לך'.") in prompt
    assert "לא ממליצים ולא מציעים חלופות אחרות" not in prompt
    assert "'מה הכי חשוב לך: שיישאר יותר כסף בנטו, בטיחות, מקום, או משהו אחר?'" in prompt


def test_prompt_translates_a_vague_wish_into_filters_openly(prompt):
    assert "'נוח מבחינת מה?'" in prompt
    # 'family car' at Strauss is also the family track (4+ children): ask which one is meant
    assert "'למסלול המשפחתי, או רכב מרווח למשפחה?'" in prompt
    assert "מרווח ← מושבים וסוג מרכב" in prompt
    for phrase in ("מקום ← מושבים וסוג מרכב", "חניה ← מצלמת רוורס", "נסיעות ארוכות ← שיוט אדפטיבי",
                   "ישיבה גבוהה ← גובה וסוג מרכב", "אומרים לעובד בגלוי איך תרגמת, והוא יכול לתקן."):
        assert phrase in prompt, phrase


def test_prompt_specs_only_from_the_tools(prompt):
    assert "על יופי, שקט, תחושת נסיעה ותא מטען אין נתון רשמי" in prompt
    assert "נסיעת מבחן" in prompt
    assert "אסור לכתוב נתוני מפרט מהזיכרון, רק מתוצאה של car_specs או rank_options." in prompt
    assert "'נתון ראשוני'" in prompt and "'בקירוב'" in prompt
    assert "'לפרטים המלאים: [המפרט אצל היבואן]'" in prompt


def test_prompt_catalog_list_is_for_names_only(prompt):
    assert "לזיהוי שמות בלבד. מציגים רכבים רק מתוצאה של rank_options." in prompt
    assert '"איזה רכב כדאי לי?"' in prompt


def test_prompt_tone_example_offers_to_sort(prompt):
    assert "אני לא ממליץ על רכבים" not in prompt
    assert ("מבין, זו החלטה לא פשוטה. אני יכול לסדר לך את הרכבים שמגיעים לך לפי מה שהכי חשוב לך,\n"
            "ולהראות מה יקרה לנטו בכל אחד.") in prompt


def test_prompt_offers_the_payslip_only_at_the_salary_question(prompt):
    t = load_agent_config(BACKEND_DIR)["texts"]["payslip"]
    assert t["offer"] in prompt and t["taken"] in prompt and t["notePrefix"] in prompt
    salary_question = prompt.index("2. שכר בסיס")
    assert prompt.index(t["offer"]) > salary_question  # offered where the salary is asked, not up front
