"""Wiring of the LangGraph agent, with a scripted fake model (no API calls)."""
import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.advisor import load_agent_config
from app.agent.graph import TOOL_NAMES, build_agent
from app.agent.prompt import build_prompt
from app.agent.rep_queue import InMemoryRepQueue
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args


class ScriptedModel(GenericFakeChatModel):
    """Replays fixed AI messages; tool binding is a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args, idx=0):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"{name}-{idx}"}])


def run(data, script, user_text="שאלה", thread="t"):
    queue = InMemoryRepQueue()
    agent = build_agent(ScriptedModel(messages=iter(script)), data, queue, load_agent_config(BACKEND_DIR))
    out = agent.invoke({"messages": [("user", user_text)]}, {"configurable": {"thread_id": thread}})
    return out, queue


def tool_results(out, name):
    return [json.loads(m.content) for m in out["messages"] if isinstance(m, ToolMessage) and m.name == name]


def test_four_tools(data):
    assert TOOL_NAMES == {"lookup_vehicle", "check_eligibility", "calculate", "ask_rep"}


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
    for phrase in ("מועתק כמו שהוא", "אסור לחשב", "לשנתי", "לאחוזים", "לא ממליצים",
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
