"""Timing logs: where does the time of one answer go (data, tools, each model call)?"""
import logging

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent.models import WithTimeout
from app.timing import timed
from tests.test_agent_advisor import employee_args
from tests.test_agent_graph import call, run

TIMING = "app.timing"


def lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == TIMING]


def test_timed_logs_the_label_and_seconds(caplog):
    with caplog.at_level(logging.INFO, logger=TIMING):
        with timed("something"):
            pass
    [line] = lines(caplog)
    assert "something" in line and "s" in line


def test_timed_logs_a_failure_too(caplog):
    with caplog.at_level(logging.INFO, logger=TIMING):
        try:
            with timed("broken"):
                raise ValueError("x")
        except ValueError:
            pass
    [line] = lines(caplog)
    assert "broken" in line and "ValueError" in line


def test_each_model_call_is_logged_with_its_name(caplog):
    model = WithTimeout(GenericFakeChatModel(messages=iter([AIMessage(content="שלום")])), 5, label="gemini_2")
    with caplog.at_level(logging.INFO, logger=TIMING):
        model.invoke("היי")
    assert any("gemini_2" in line for line in lines(caplog))


def test_each_tool_call_is_logged(caplog, data):
    script = [call("calculate", employee_args(data, "E-001")), AIMessage(content="סיום")]
    with caplog.at_level(logging.INFO, logger=TIMING):
        run(data, script)
    assert any("calculate" in line for line in lines(caplog))
