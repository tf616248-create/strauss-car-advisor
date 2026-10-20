"""Model chain: Gemini Flash first, then Groq, then OpenRouter. ANY error moves on to the next key or
model (a 429, a 5xx, a connection error, a timeout, and also an invalid key - 401 - or a bad request),
except a model that went silent mid-answer (see below).

Keys and model names come only from the environment (.env) - see .env.example.
A provider without a key is skipped. Gemini's free quota is per Google project,
so GOOGLE_API_KEY_2 .. _9 (keys from other projects) are tried in order after
GOOGLE_API_KEY, before Groq.

Every call has a clock (modelTimeoutSeconds in config/agent.json) that counts until the
model's FIRST word: a model that never starts answering (e.g. waiting out a quota) counts like
a 503 and the next one is tried. A model that is already writing is never cut off and never
replaced - its words are on the employee's screen. If it then goes silent for that long, the
answer ends with an error (ModelStalledError), not with a second answer from another model.
An abandoned call runs without callbacks, so its words can't reach the screen.

Gemini's "thinking" is turned down (geminiThinkingLevel in config/agent.json): the agent only
calls tools and copies their numbers, so thinking adds latency without adding accuracy.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Iterator, Mapping, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import generate_from_stream
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict

from app.timing import log as timing_log


class ModelTimeoutError(TimeoutError):
    """A model didn't start answering within modelTimeoutSeconds."""


class ModelStalledError(BaseException):
    """A model started answering, then went silent. Deliberately NOT a reason to switch models:
    its words are already on screen, and a second model would write a second answer below them.
    A BaseException, so the fallbacks (which catch every Exception) let it through; whoever runs
    the agent catches it by name (app/api/employee.py)."""


# Every error moves on to the next key/model: 429 (quota), 5xx (e.g. 503 overload), an unreachable
# provider (e.g. blocked by a network filter), a call that hangs, an invalid key (401) - one broken
# key must not stop the others. ModelStalledError is not an Exception, so it is never caught here.
SWITCH_ERRORS = (Exception,)

DEFAULTS = {
    "GEMINI_MODEL": "gemini-3.7-flash",
    "GROQ_MODEL": "llama-3.3-70b-versatile",
    "OPENROUTER_MODEL": "google/gemma-4-31b-it:free",
}


# GEMINI_API_KEY is the name on Render; GOOGLE_API_KEY(_2.._9) the names in a local .env
GEMINI_KEY_VARS = ["GEMINI_API_KEY", "GOOGLE_API_KEY"] + [f"GOOGLE_API_KEY_{i}" for i in range(2, 10)]


def available_models(env: Mapping[str, str], thinking_level: Optional[str] = None) -> list[tuple[str, object]]:
    def name(var):
        return env.get(var) or DEFAULTS[var]

    out = []
    for var in GEMINI_KEY_VARS:
        if env.get(var):
            from langchain_google_genai import ChatGoogleGenerativeAI

            label = "gemini" + var.split("API_KEY", 1)[1].lower()
            # max_retries=2: enough for a passing 503 overload, short enough that a
            # spent quota (429) moves on to the next key quickly
            out.append((label, ChatGoogleGenerativeAI(
                model=name("GEMINI_MODEL"), google_api_key=env[var], temperature=0, max_retries=2,
                thinking_level=thinking_level)))
    if env.get("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        out.append(("groq", ChatGroq(model=name("GROQ_MODEL"), api_key=env["GROQ_API_KEY"], temperature=0)))
    if env.get("OPENROUTER_API_KEY"):
        from langchain_openai import ChatOpenAI

        out.append(("openrouter", ChatOpenAI(
            model=name("OPENROUTER_MODEL"), api_key=env["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1", temperature=0)))
    return out


_DONE = object()


class WithTimeout(BaseChatModel):
    """A chat model that streams another model's answer through a clock.

    The inner model runs in a worker thread with no callbacks; this wrapper re-emits its words
    (LangGraph streams them from here). So when the clock runs out before the first word, the
    abandoned call keeps going in the background but stays silent. bind_tools keeps the clock,
    since create_react_agent binds tools on the whole chain.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: Any
    seconds: float
    label: str = "model"

    def __init__(self, model: Runnable, seconds: float, label: str = "model", fallback: bool = False,
                 **kwargs: Any):
        # metadata/tags go on this call's trace (app/tracing.py): which model, and whether it is a fallback
        super().__init__(model=model, seconds=seconds, label=label,
                         metadata={"kobi_model": label, "kobi_fallback": fallback},
                         tags=["fallback"] if fallback else [], **kwargs)

    @property
    def _llm_type(self) -> str:
        return f"with-timeout:{self.label}"

    def _get_ls_params(self, stop: Optional[list[str]] = None, **kwargs: Any) -> dict:
        inner = getattr(self.model, "bound", self.model)  # after bind_tools: a binding around the model
        name = getattr(inner, "model", None) or getattr(inner, "model_name", None)
        return {"ls_provider": self.label.split("_", 1)[0], "ls_model_name": name if isinstance(name, str) else self.label,
                "ls_model_type": "chat"}

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return WithTimeout(self.model.bind_tools(tools, **kwargs), self.seconds, self.label,
                           fallback=self.metadata["kobi_fallback"])

    def _stream(self, messages: list[BaseMessage], stop: Optional[list[str]] = None,
                run_manager=None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        inbox: queue.Queue = queue.Queue()
        abandoned = threading.Event()

        def work():
            try:
                # callbacks=[]: nothing from this call reaches the employee except what we yield
                for chunk in self.model.stream(messages, config={"callbacks": []}, stop=stop, **kwargs):
                    if abandoned.is_set():
                        return
                    inbox.put(chunk)
                inbox.put(_DONE)
            except BaseException as e:  # noqa: BLE001 - handed to the caller below
                inbox.put(e)

        threading.Thread(target=work, daemon=True, name=f"model-{self.label}").start()
        started = time.perf_counter()
        first_word = None
        outcome = "ok"
        try:
            while True:
                try:
                    item = inbox.get(timeout=self.seconds)
                except queue.Empty:
                    if first_word is None:
                        outcome = "no first word"
                        raise ModelTimeoutError(f"no answer within {self.seconds}s") from None
                    outcome = "went silent mid-answer"
                    raise ModelStalledError(f"silent for {self.seconds}s mid-answer") from None
                if item is _DONE:
                    return
                if isinstance(item, BaseException):
                    outcome = type(item).__name__
                    raise item
                if first_word is None:
                    first_word = time.perf_counter() - started
                    # which model answered, for the cost of the question (app/usage.py); first chunk
                    # only, since chunks are merged and strings in response_metadata would concatenate
                    item.response_metadata = {**item.response_metadata, "kobi_model": self.label}
                yield ChatGenerationChunk(message=item)
        finally:
            abandoned.set()
            first = "-" if first_word is None else f"{first_word:.3f}s"
            timing_log.info("⏱ model %s: first output %s, total %.3fs (%s)",
                            self.label, first, time.perf_counter() - started, outcome)

    def _generate(self, messages: list[BaseMessage], stop: Optional[list[str]] = None,
                  run_manager=None, **kwargs: Any) -> ChatResult:
        return generate_from_stream(self._stream(messages, stop, run_manager, **kwargs))


def with_fallbacks(models: list, timeout_seconds: Optional[float] = None, labels: Optional[list[str]] = None):
    if timeout_seconds is not None:
        labels = labels or ["model"] * len(models)
        models = [WithTimeout(m, timeout_seconds, label, fallback=i > 0)
                  for i, (m, label) in enumerate(zip(models, labels))]
    if len(models) == 1:
        return models[0]
    return models[0].with_fallbacks(models[1:], exceptions_to_handle=SWITCH_ERRORS)


def build_model(timeout_seconds: float, env: Optional[Mapping[str, str]] = None,
                thinking_level: Optional[str] = None):
    """timeout_seconds / thinking_level: modelTimeoutSeconds / geminiThinkingLevel from config/agent.json."""
    named = available_models(os.environ if env is None else env, thinking_level)
    models = [m for _, m in named]
    if not models:
        raise RuntimeError("No model key set. Fill GOOGLE_API_KEY (and backups GROQ_API_KEY, "
                           "OPENROUTER_API_KEY) in backend/.env - see .env.example.")
    return with_fallbacks(models, timeout_seconds, [name for name, _ in named])
