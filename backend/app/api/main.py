"""HTTP API.

  POST /chat                       SSE: thread, step, token, card, done | error
  GET  /chat/{thread_id}           restore a conversation (messages + cards)
  GET  /chat/{thread_id}/rep       polling fallback for rep answers
  GET  /rep/requests               rep screen: open questions (+ the employee's card)
  POST /rep/requests/{id}/answer   rep answers; the conversation is notified (Broadcast)
  GET  /health

The employee is not identified: a conversation is a random UUID kept by the browser.
The rep screen uses a shared passcode (REP_PASSCODE) - real login is a pilot item.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from pydantic import BaseModel, Field

from app.agent.graph import build_agent

log = logging.getLogger(__name__)

UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class InMemoryNotifier:
    """Stand-in for Supabase Broadcast (stage 7, when keys exist)."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def notify(self, thread_id: str, event: dict) -> None:
        self.sent.append((thread_id, event))


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: Optional[str] = Field(default=None, pattern=UUID_RE)


class AnswerIn(BaseModel):
    values: dict[str, str | int | float]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type", "text") == "text")


def _cards(messages) -> list[dict]:
    out = []
    for m in messages:
        if m.type == "tool" and m.name == "calculate":
            res = json.loads(m.content)
            if "card" in res:
                out.append({"status": res["status"], "card": res["card"]})
    return out


def create_app(*, data, model, rep_queue, notifier, cfg: dict, rep_passcode: Optional[str],
               checkpointer=None, origins: tuple[str, ...] = ("http://localhost:5173",)) -> FastAPI:
    agent = build_agent(model, data, rep_queue, cfg, checkpointer)
    texts = cfg["texts"]
    app = FastAPI(title="Strauss car advisor")
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"])

    def config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def messages_of(thread_id: str) -> list:
        return agent.get_state(config(thread_id)).values.get("messages", [])

    def require_rep(x_rep_passcode: Optional[str] = Header(default=None)) -> None:
        if not rep_passcode:
            raise HTTPException(503, "rep screen is not configured (REP_PASSCODE)")
        if not x_rep_passcode or not secrets.compare_digest(x_rep_passcode, rep_passcode):
            raise HTTPException(401, "wrong passcode")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/chat")
    def chat(body: ChatIn):
        thread_id = body.thread_id or str(uuid.uuid4())

        def stream():
            if not body.thread_id:
                yield _sse("thread", {"thread_id": thread_id})
            try:
                for mode, chunk in agent.stream({"messages": [("user", body.message)]}, config(thread_id),
                                                stream_mode=["messages", "updates"]):
                    if mode == "messages":
                        msg, meta = chunk
                        if isinstance(msg, AIMessageChunk) and meta.get("langgraph_node") == "agent":
                            text = _text(msg.content)
                            if text:
                                yield _sse("token", {"text": text})
                    elif "agent" in chunk:
                        for msg in chunk["agent"].get("messages", []):
                            for tc in getattr(msg, "tool_calls", []) or []:
                                yield _sse("step", {"tool": tc["name"], "label": texts["steps"].get(tc["name"], "")})
                    elif "tools" in chunk:
                        for card in _cards(chunk["tools"].get("messages", [])):
                            yield _sse("card", card)
                yield _sse("done", {})
            except Exception:  # every model failed, or a bug - the employee gets a calm message
                log.exception("chat failed (thread %s)", thread_id)
                yield _sse("error", {"message": texts["overloaded"]})

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/chat/{thread_id}")
    def restore(thread_id: str = Path(pattern=UUID_RE)):
        msgs = messages_of(thread_id)
        if not msgs:
            raise HTTPException(404, "unknown conversation")
        shown = []
        for m in msgs:
            if m.type == "human":
                shown.append({"role": "user", "text": _text(m.content)})
            elif m.type == "ai" and _text(m.content):
                shown.append({"role": "assistant", "text": _text(m.content)})
        return {"thread_id": thread_id, "messages": shown, "cards": _cards(msgs)}

    @app.get("/chat/{thread_id}/rep")
    def rep_status(thread_id: str = Path(pattern=UUID_RE)):
        return {"pending": len(rep_queue.pending(thread_id)), "answered": rep_queue.answered_ids(thread_id)}

    @app.get("/rep/requests", dependencies=[Depends(require_rep)])
    def rep_requests():
        out = []
        for req in rep_queue.all_pending():
            cards = _cards(messages_of(req["thread_id"]))
            out.append({"id": req["id"], "thread_id": req["thread_id"], "fields": req["fields"],
                        "question": req["question"], "car_key": req["car_key"],
                        "card": cards[-1]["card"] if cards else None})
        return out

    @app.post("/rep/requests/{request_id}/answer", dependencies=[Depends(require_rep)])
    def rep_answer(request_id: str, body: AnswerIn):
        req = rep_queue.get(request_id)
        if req is None:
            raise HTTPException(404, "unknown request")
        rep_queue.answer(request_id, body.values)
        notifier.notify(req["thread_id"], {"type": "rep_answered", "request_id": request_id})
        return {"status": "ok"}

    return app
