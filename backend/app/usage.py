"""Cost of each question: every model call's tokens (usage_metadata), summed per question.

A question can take several model calls (the model calls a tool, reads the result, answers).
Prices per million tokens live in config/agent.json ("usage.prices", per provider: gemini, groq,
openrouter). A provider without a price gives no cost (empty), not a guess. Output tokens include
Gemini's thinking tokens, which are billed at the output price.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from langchain_core.messages import AIMessage

COLUMNS = ["time", "question", "calls", "input_tokens", "output_tokens", "models", "cost_usd", "thread_id"]


def _provider(label: str) -> str:
    return label.split("_", 1)[0]  # gemini_2 -> gemini


def turn_usage(messages: list, prices: dict) -> dict:
    calls = inp = out = 0
    cost: Optional[float] = 0.0
    models: list[str] = []
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        calls += 1
        u = m.usage_metadata or {}
        i, o = u.get("input_tokens", 0), u.get("output_tokens", 0)
        inp, out = inp + i, out + o
        label = m.response_metadata.get("kobi_model", "model")
        if label not in models:
            models.append(label)
        price = prices.get(_provider(label))
        if price is None or cost is None:
            cost = None
        else:
            cost += (i * price["inputPerMillionUsd"] + o * price["outputPerMillionUsd"]) / 1_000_000
    return {"calls": calls, "input_tokens": inp, "output_tokens": out, "models": "+".join(models), "cost_usd": cost}


def append_row(path: Path, row: dict) -> None:
    """One row per question. utf-8-sig so Excel shows the Hebrew; the header only in a new file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in COLUMNS})
