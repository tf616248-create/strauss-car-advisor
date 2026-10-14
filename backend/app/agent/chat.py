"""Console chat for a live try (needs keys in backend/.env).

    cd backend
    python -m app.agent.chat

Type as the employee. Rep commands (the rep's screen comes in stage 7):
    /rep                         list pending rep questions
    /rep 1 participation=250     answer request 1 (several field=value allowed)
    /card                        print the last comparison card
    /exit
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agent.advisor import load_agent_config
from app.agent.graph import build_agent
from app.agent.models import build_model
from app.agent.rep_queue import InMemoryRepQueue
from app.data.loader import load_all

BACKEND_DIR = Path(__file__).resolve().parents[2]
THREAD = "console"


def _value(text: str):
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return text


def _rep_command(queue: InMemoryRepQueue, parts: list[str]) -> bool:
    """Returns True when an answer was saved (the agent is then notified)."""
    if len(parts) == 1:
        for req in queue.pending(THREAD):
            print(f'  [{req["id"]}] {req["fields"]} car={req["car_key"]}: {req["question"]}')
        if not queue.pending(THREAD):
            print("  (אין שאלות פתוחות)")
        return False
    values = dict(p.split("=", 1) for p in parts[2:])
    queue.answer(parts[1], {k: _value(v) for k, v in values.items()})
    return True


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BACKEND_DIR / ".env")
    data = load_all(BACKEND_DIR)
    queue = InMemoryRepQueue()
    config = {"configurable": {"thread_id": THREAD}}
    cfg = load_agent_config(BACKEND_DIR)
    agent = build_agent(build_model(), data, queue, cfg)
    last_card = None

    while True:
        try:
            text = input("\nעובד> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/exit":
            break
        if text.startswith("/rep"):
            if not _rep_command(queue, text.split()):
                continue
            text = cfg["texts"]["repAnswered"]  # in stage 7 Supabase Realtime sends this
            print(f"  {text}")
        if text == "/card":
            print(json.dumps(last_card, ensure_ascii=False, indent=2) if last_card else "  (עוד אין כרטיס)")
            continue

        print("בוט> ", end="", flush=True)
        for chunk, _meta in agent.stream({"messages": [("user", text)]}, config, stream_mode="messages"):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                content = chunk.content if isinstance(chunk.content, str) else "".join(
                    part.get("text", "") for part in chunk.content if isinstance(part, dict))
                print(content, end="", flush=True)
            elif isinstance(chunk, ToolMessage):
                result = json.loads(chunk.content)
                print(f"\n  … {chunk.name}: {result.get('status')}", flush=True)
                if chunk.name == "calculate" and "card" in result:
                    last_card = result["card"]
        print()


if __name__ == "__main__":
    main()
