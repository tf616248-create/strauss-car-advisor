"""Model chain: Gemini first, then Groq, then OpenRouter. Keys only from the environment."""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.agent.models import (SWITCH_ERRORS, ModelStalledError, ModelTimeoutError, available_models, build_model,
                              with_fallbacks)

ALL_KEYS = {"GOOGLE_API_KEY": "g", "GROQ_API_KEY": "q", "OPENROUTER_API_KEY": "o"}


def test_order_is_gemini_groq_openrouter():
    assert [name for name, _ in available_models(ALL_KEYS)] == ["gemini", "groq", "openrouter"]


def test_missing_key_is_skipped():
    env = {"GROQ_API_KEY": "q"}
    assert [name for name, _ in available_models(env)] == ["groq"]


def test_no_keys_fails_loudly():
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        build_model(30, {})


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

    assert issubclass(groq.RateLimitError, SWITCH_ERRORS)
    assert issubclass(openai.RateLimitError, SWITCH_ERRORS)


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
    bound = build_model(30, ALL_KEYS).bind_tools(tools)
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


class Overloaded(GenericFakeChatModel):
    def _generate(self, *args, **kwargs):
        from langchain_core.exceptions import ModelAPIError

        raise ModelAPIError("503 UNAVAILABLE: high demand")

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self


def test_falls_back_on_server_overload_503():
    chain = with_fallbacks([Overloaded(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))])
    assert chain.invoke("שלום").content == "גיבוי"


def test_provider_server_errors_are_handled():
    import groq
    import openai
    from langchain_core.exceptions import ModelAPIError

    for cls in (groq.InternalServerError, openai.InternalServerError, ModelAPIError):
        assert issubclass(cls, SWITCH_ERRORS)


def test_connection_errors_move_on_too():
    """A provider that can't be reached (e.g. blocked by a network filter) must not stop the chain."""
    import groq
    import openai
    from langchain_core.exceptions import ModelConnectionError

    for cls in (groq.APIConnectionError, openai.APIConnectionError, ModelConnectionError):
        assert issubclass(cls, SWITCH_ERRORS)


class Unreachable(GenericFakeChatModel):
    def _generate(self, *args, **kwargs):
        import groq
        import httpx

        raise groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self


def test_falls_back_when_provider_unreachable():
    chain = with_fallbacks([Unreachable(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))])
    assert chain.invoke("שלום").content == "גיבוי"


# --- a model that never answers (quota wait / overload with no error) -------------

import threading
import time

RELEASE = threading.Event()  # lets the abandoned call threads finish after each test


@pytest.fixture(autouse=True)
def _release_hanging_calls():
    RELEASE.clear()
    yield
    RELEASE.set()


class Hanging(GenericFakeChatModel):
    calls: int = 0

    def _generate(self, *args, **kwargs):
        self.calls += 1
        RELEASE.wait(10)
        raise AssertionError("an abandoned call must not be used")

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self


def test_timeout_comes_from_agent_config():
    from app.agent.advisor import load_agent_config
    from tests.conftest import BACKEND_DIR

    seconds = load_agent_config(BACKEND_DIR)["modelTimeoutSeconds"]
    assert isinstance(seconds, (int, float)) and 0 < seconds <= 120


def test_timeout_is_handled_like_a_rate_limit():
    assert issubclass(ModelTimeoutError, SWITCH_ERRORS)


def test_hanging_model_times_out():
    chain = with_fallbacks([Hanging(messages=iter([]))], timeout_seconds=0.2)
    start = time.monotonic()
    with pytest.raises(ModelTimeoutError):
        chain.invoke("שלום")
    assert time.monotonic() - start < 2


def test_falls_back_when_model_hangs():
    hanging = Hanging(messages=iter([]))
    chain = with_fallbacks([hanging, Fake(messages=iter([AIMessage(content="גיבוי")]))], timeout_seconds=0.2)
    assert chain.invoke("שלום").content == "גיבוי"
    assert hanging.calls == 1


def test_timeout_survives_binding_tools(data):
    """create_react_agent calls bind_tools; every model in the chain must keep its timeout."""
    from app.agent.advisor import load_agent_config
    from app.agent.graph import make_tools
    from app.agent.rep_queue import InMemoryRepQueue
    from tests.conftest import BACKEND_DIR

    tools = make_tools(data, InMemoryRepQueue(), load_agent_config(BACKEND_DIR))
    hanging = Hanging(messages=iter([]))
    bound = with_fallbacks([hanging, Fake(messages=iter([AIMessage(content="גיבוי")]))],
                           timeout_seconds=0.2).bind_tools(tools)
    assert bound.invoke("שלום").content == "גיבוי"


def test_real_models_get_the_timeout():
    from app.agent.models import WithTimeout

    chain = build_model(7, ALL_KEYS)
    for m in [chain.runnable, *chain.fallbacks]:
        assert isinstance(m, WithTimeout) and m.seconds == 7


# --- Gemini "thinking": off-ish for speed (a tool-calling agent that copies numbers) ---

def test_thinking_level_comes_from_agent_config():
    from app.agent.advisor import load_agent_config
    from tests.conftest import BACKEND_DIR

    assert load_agent_config(BACKEND_DIR)["geminiThinkingLevel"] in ("minimal", "low", "medium", "high")


def test_gemini_gets_the_thinking_level():
    models = dict(available_models(dict(ALL_KEYS, GOOGLE_API_KEY_2="g2"), thinking_level="minimal"))
    assert models["gemini"].thinking_level == "minimal"
    assert models["gemini_2"].thinking_level == "minimal"


def test_without_thinking_level_gemini_keeps_its_default():
    assert dict(available_models(ALL_KEYS))["gemini"].thinking_level is None


def test_build_model_passes_the_thinking_level():
    chain = build_model(7, ALL_KEYS, thinking_level="low")
    assert chain.runnable.model.thinking_level == "low"


# --- every error moves to the next key, except a model that went silent mid-answer ----


class BadKey(GenericFakeChatModel):
    """Like Gemini with an invalid key: 401, not a rate limit."""

    def _generate(self, *args, **kwargs):
        raise PermissionError("401 UNAUTHENTICATED: API key not valid")

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self


class Broken(GenericFakeChatModel):
    def _generate(self, *args, **kwargs):
        raise ValueError("400 bad request")

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self


@pytest.mark.parametrize("failing", [BadKey, Broken])
def test_any_error_moves_to_the_next_key(failing):
    chain = with_fallbacks([failing(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))])
    assert chain.invoke("שלום").content == "גיבוי"


@pytest.mark.parametrize("failing", [BadKey, Broken])
def test_any_error_moves_on_with_the_clock_too(failing):
    chain = with_fallbacks([failing(messages=iter([])), Fake(messages=iter([AIMessage(content="גיבוי")]))], 5)
    assert chain.invoke("שלום").content == "גיבוי"


def test_a_model_that_went_silent_mid_answer_never_switches():
    """Its words are already on the employee's screen: a second model would write a second answer."""
    assert not issubclass(ModelStalledError, SWITCH_ERRORS)
