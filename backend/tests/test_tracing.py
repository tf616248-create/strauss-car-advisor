"""LangSmith tracing: on only through the environment (LANGSMITH_TRACING + LANGSMITH_API_KEY), no key in
code. Without them everything works and nothing is sent. Each trace carries the conversation id, the
model that answered, whether it was a fallback, and the tag "eval" for an eval run."""
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langsmith.utils import tracing_is_enabled

from app import tracing
from app.agent.models import with_fallbacks
from app.api.common import thread_config
from tests.test_agent_models import Fake, Overloaded


@pytest.fixture(autouse=True)
def tracing_off_after():
    yield
    tracing.configure({})


ON = {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2-test-not-a-real-key", "LANGSMITH_PROJECT": "kobi-test"}


def test_off_without_the_variables():
    assert tracing.configure({}) is False
    assert not tracing_is_enabled()


def test_off_when_tracing_is_on_but_there_is_no_key():
    assert tracing.configure({"LANGSMITH_TRACING": "true"}) is False
    assert not tracing_is_enabled()


def test_off_when_the_key_is_there_but_tracing_is_not_on():
    assert tracing.configure({"LANGSMITH_API_KEY": "k"}) is False
    assert not tracing_is_enabled()


def test_on_with_both():
    assert tracing.configure(ON) is True
    assert tracing_is_enabled()


def test_every_run_carries_the_conversation_id():
    cfg = thread_config("tid-1")
    assert cfg["configurable"] == {"thread_id": "tid-1"}
    assert cfg["metadata"]["thread_id"] == "tid-1"  # LangSmith groups a conversation's traces by it
    assert "eval" not in cfg.get("tags", [])


def test_an_eval_run_is_tagged():
    cfg = tracing.eval_config("eval-xyz", "main flow", "demo-pdf-electric")
    assert cfg["configurable"] == {"thread_id": "eval-xyz"}
    assert "eval" in cfg["tags"]
    assert cfg["metadata"] == {"thread_id": "eval-xyz", "eval_set": "main flow", "eval_case": "demo-pdf-electric"}


class Recorder(BaseCallbackHandler):
    def __init__(self):
        self.starts = []

    def on_chat_model_start(self, serialized, messages, *, metadata=None, tags=None, **kwargs):
        self.starts.append({"metadata": metadata or {}, "tags": tags or []})


def test_each_model_call_says_which_model_and_whether_it_is_a_fallback():
    chain = with_fallbacks([Overloaded(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))],
                           timeout_seconds=5, labels=["gemini", "groq"])
    rec = Recorder()
    assert chain.invoke("שאלה", config={"callbacks": [rec]}).content == "גיבוי"
    first, second = rec.starts
    assert first["metadata"]["kobi_model"] == "gemini" and first["metadata"]["kobi_fallback"] is False
    assert second["metadata"]["kobi_model"] == "groq" and second["metadata"]["kobi_fallback"] is True
    assert "fallback" in second["tags"] and "fallback" not in first["tags"]
    assert second["metadata"]["ls_provider"] == "groq"
    assert isinstance(second["metadata"].get("ls_model_name"), str)  # a name, not the wrapped model object


def test_the_labels_survive_binding_tools():
    chain = with_fallbacks([Fake(messages=iter([AIMessage(content="x")]))], timeout_seconds=5, labels=["gemini"])
    rec = Recorder()
    chain.bind_tools([]).invoke("שאלה", config={"callbacks": [rec]})
    assert rec.starts[0]["metadata"]["kobi_model"] == "gemini"


# --- nothing is sent without the variables ------------------------------------------------------


@pytest.fixture
def senders(monkeypatch):
    """Anything that would talk to LangSmith: its tracer or its client. Recorded, and stopped."""
    made = []

    def stop(name):
        def init(self, *args, **kwargs):
            made.append(name)
            raise RuntimeError(f"{name}: would send to LangSmith")
        return init

    import langchain_core.tracers.langchain as lc_tracer
    import langsmith.client
    monkeypatch.setattr(lc_tracer.LangChainTracer, "__init__", stop("LangChainTracer"))
    monkeypatch.setattr(langsmith.client.Client, "__init__", stop("Client"))
    return made


def ask(data):
    from app.agent.advisor import load_agent_config
    from tests.conftest import BACKEND_DIR
    from tests.test_api import chat, make
    client, _, _ = make(data, load_agent_config(BACKEND_DIR), script=[AIMessage(content="שלום, אני כובי")])
    return chat(client, "שלום")


def test_without_the_variables_a_whole_conversation_sends_nothing(data, senders, monkeypatch):
    for var in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    tracing.configure({})
    evs = ask(data)
    assert ("done" in [k for k, _ in evs]) and senders == []


def test_the_check_above_would_catch_a_send(data, senders):
    """Control: with tracing on, the same conversation does try to create the tracer."""
    tracing.configure(ON)
    try:
        ask(data)
    except Exception:  # noqa: BLE001 - the stopped tracer may fail the request; only the attempt matters
        pass
    assert senders
