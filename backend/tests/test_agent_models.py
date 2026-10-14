"""Model chain: Gemini first, then Groq, then OpenRouter. Keys only from the environment."""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.agent.models import RATE_LIMIT_ERRORS, available_models, build_model, with_fallbacks

ALL_KEYS = {"GOOGLE_API_KEY": "g", "GROQ_API_KEY": "q", "OPENROUTER_API_KEY": "o"}


def test_order_is_gemini_groq_openrouter():
    assert [name for name, _ in available_models(ALL_KEYS)] == ["gemini", "groq", "openrouter"]


def test_missing_key_is_skipped():
    env = {"GROQ_API_KEY": "q"}
    assert [name for name, _ in available_models(env)] == ["groq"]


def test_no_keys_fails_loudly():
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        build_model({})


def test_model_names_come_from_env():
    env = dict(ALL_KEYS, GEMINI_MODEL="gemini-x", GROQ_MODEL="groq-x", OPENROUTER_MODEL="or-x")
    names = {name: m for name, m in available_models(env)}
    assert names["gemini"].model.endswith("gemini-x")
    assert names["groq"].model_name == "groq-x"
    assert names["openrouter"].model_name == "or-x"


def rate_limit_error():
    import groq
    import httpx

    request = httpx.Request("POST", "https://api.groq.com")
    return groq.RateLimitError("429", response=httpx.Response(429, request=request), body=None)


def test_provider_rate_limit_errors_are_handled():
    import groq
    import openai

    assert groq.RateLimitError in RATE_LIMIT_ERRORS
    assert openai.RateLimitError in RATE_LIMIT_ERRORS


class Failing(GenericFakeChatModel):
    def _generate(self, *args, **kwargs):
        raise rate_limit_error()

    def bind_tools(self, tools, **kwargs) -> Runnable:  # annotated like real models,
        return self  # so with_fallbacks binds tools on every model


class Fake(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs) -> Runnable:  # annotated like real models,
        return self  # so with_fallbacks binds tools on every model


def test_falls_back_on_rate_limit():

    chain = with_fallbacks([Failing(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))])
    assert chain.invoke("שלום").content == "גיבוי"


def test_real_models_keep_fallbacks_after_binding_tools(data):
    """create_react_agent calls bind_tools; the fallbacks must survive it."""
    from langchain_core.runnables.fallbacks import RunnableWithFallbacks

    from app.agent.advisor import load_agent_config
    from app.agent.graph import make_tools
    from app.agent.rep_queue import InMemoryRepQueue
    from tests.conftest import BACKEND_DIR

    tools = make_tools(data, InMemoryRepQueue(), load_agent_config(BACKEND_DIR))
    bound = build_model(ALL_KEYS).bind_tools(tools)
    assert isinstance(bound, RunnableWithFallbacks)
    assert len(bound.fallbacks) == 2


def test_agent_falls_back_on_rate_limit(data):
    from app.agent.advisor import load_agent_config
    from app.agent.graph import build_agent
    from app.agent.rep_queue import InMemoryRepQueue
    from tests.conftest import BACKEND_DIR

    backup = Fake(messages=iter([AIMessage(content="מהגיבוי")]))
    agent = build_agent(with_fallbacks([Failing(messages=iter([])), backup]), data,
                        InMemoryRepQueue(), load_agent_config(BACKEND_DIR))
    out = agent.invoke({"messages": [("user", "שלום")]}, {"configurable": {"thread_id": "t"}})
    assert out["messages"][-1].content == "מהגיבוי"


def test_several_gemini_keys_are_tried_in_order():
    """Free quota is per Google project: a key from another project continues after a 429."""
    env = dict(ALL_KEYS, GOOGLE_API_KEY_2="g2", GOOGLE_API_KEY_3="g3")
    assert [name for name, _ in available_models(env)] == ["gemini", "gemini_2", "gemini_3", "groq", "openrouter"]


def test_extra_gemini_key_without_the_first_still_counts():
    env = {"GOOGLE_API_KEY_2": "g2"}
    assert [name for name, _ in available_models(env)] == ["gemini_2"]


def test_gemini_retries_briefly_then_next_key():
    """A couple of retries survive a passing 503 overload; then a 429 moves on to the next key."""
    gemini = dict(available_models(dict(ALL_KEYS, GOOGLE_API_KEY_2="g2")))["gemini"]
    assert 1 <= gemini.max_retries <= 2
