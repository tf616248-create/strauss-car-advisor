"""Shared by the employee and rep routes: SSE formatting and reading a conversation's state."""
from __future__ import annotations

import json

from fastapi.responses import StreamingResponse

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class EventStreamResponse(StreamingResponse):
    """Closes the stream when the browser leaves, so it is removed from the listeners
    at once (Starlette leaves the generator open when sending fails)."""

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type", "text") == "text")


def cards_of(messages) -> list[dict]:
    out = []
    for m in messages:
        if m.type == "tool" and m.name == "calculate":
            res = json.loads(m.content)
            if "card" in res:
                out.append({"status": res["status"], "card": res["card"]})
    return out


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def messages_of(agent, thread_id: str) -> list:
    return agent.get_state(thread_config(thread_id)).values.get("messages", [])
