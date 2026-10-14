"""Model chain: Gemini Flash first, then Groq, then OpenRouter, switching on a 429, a 5xx or a connection error.

Keys and model names come only from the environment (.env) - see .env.example.
A provider without a key is skipped. Gemini's free quota is per Google project,
so GOOGLE_API_KEY_2 .. _9 (keys from other projects) are tried in order after
GOOGLE_API_KEY, before Groq.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

import groq
import openai
from langchain_core.exceptions import ModelAPIError, ModelConnectionError, ModelRateLimitError

# Errors that move on to the next key/model: 429 (quota), 5xx (e.g. 503 overload),
# and an unreachable provider (e.g. blocked by a network filter).
# langchain-google-genai raises GoogleRateLimitError / GoogleAPIError (ModelRateLimitError /
# ModelAPIError); Groq and OpenAI-compatible clients raise their own classes.
RATE_LIMIT_ERRORS = (
    groq.RateLimitError, openai.RateLimitError, ModelRateLimitError,
    groq.InternalServerError, openai.InternalServerError, ModelAPIError,
    groq.APIConnectionError, openai.APIConnectionError, ModelConnectionError,
)

DEFAULTS = {
    "GEMINI_MODEL": "gemini-3.7-flash",
    "GROQ_MODEL": "llama-3.3-70b-versatile",
    "OPENROUTER_MODEL": "google/gemma-4-31b-it:free",
}


GEMINI_KEY_VARS = ["GOOGLE_API_KEY"] + [f"GOOGLE_API_KEY_{i}" for i in range(2, 10)]


def available_models(env: Mapping[str, str]) -> list[tuple[str, object]]:
    def name(var):
        return env.get(var) or DEFAULTS[var]

    out = []
    for var in GEMINI_KEY_VARS:
        if env.get(var):
            from langchain_google_genai import ChatGoogleGenerativeAI

            label = "gemini" + var[len("GOOGLE_API_KEY"):].lower()
            # max_retries=2: enough for a passing 503 overload, short enough that a
            # spent quota (429) moves on to the next key quickly
            out.append((label, ChatGoogleGenerativeAI(
                model=name("GEMINI_MODEL"), google_api_key=env[var], temperature=0, max_retries=2)))
    if env.get("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        out.append(("groq", ChatGroq(model=name("GROQ_MODEL"), api_key=env["GROQ_API_KEY"], temperature=0)))
    if env.get("OPENROUTER_API_KEY"):
        from langchain_openai import ChatOpenAI

        out.append(("openrouter", ChatOpenAI(
            model=name("OPENROUTER_MODEL"), api_key=env["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1", temperature=0)))
    return out


def with_fallbacks(models: list):
    if len(models) == 1:
        return models[0]
    return models[0].with_fallbacks(models[1:], exceptions_to_handle=RATE_LIMIT_ERRORS)


def build_model(env: Optional[Mapping[str, str]] = None):
    models = [m for _, m in available_models(os.environ if env is None else env)]
    if not models:
        raise RuntimeError("No model key set. Fill GOOGLE_API_KEY (and backups GROQ_API_KEY, "
                           "OPENROUTER_API_KEY) in backend/.env - see .env.example.")
    return with_fallbacks(models)
