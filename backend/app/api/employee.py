"""Employee routes (the chat screen, /).

  POST /chat                       SSE: thread, step, token, card, done | error
  POST /chat/{thread_id}/rep-answered   SSE: new rep answers - rerun with the system note (once per answer)
  GET  /chat/{thread_id}           the conversation's current state: messages, cards, rep status
  GET  /conversations/{thread_id}/events   SSE: "changed" (no data) + a heartbeat comment

The employee is not identified: a conversation is a random UUID kept by the browser.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from pydantic import BaseModel, Field

from app.api.common import (SSE_HEADERS, UUID_RE, EventStreamResponse, cards_of, messages_of, sse,
                            text_of, thread_config)
from app.api.events import conversation_events

log = logging.getLogger(__name__)
timing_log = logging.getLogger("app.timing")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: Optional[str] = Field(default=None, pattern=UUID_RE)


def router(*, agent, rep_queue, notifier, cfg: dict) -> APIRouter:
    texts = cfg["texts"]
    r = APIRouter(tags=["employee"])

    def run(thread_id: str, message: str, new: bool) -> StreamingResponse:
        def stream():
            if new:
                yield sse("thread", {"thread_id": thread_id})
            start = time.perf_counter()
            first_token = None
            try:
                for mode, chunk in agent.stream({"messages": [("user", message)]}, thread_config(thread_id),
                                                stream_mode=["messages", "updates"]):
                    if mode == "messages":
                        msg, meta = chunk
                        if isinstance(msg, AIMessageChunk) and meta.get("langgraph_node") == "agent":
                            text = text_of(msg.content)
                            if text:
                                if first_token is None:
                                    first_token = time.perf_counter() - start
                                    timing_log.info("⏱ answer: first word after %.3fs", first_token)
                                yield sse("token", {"text": text})
                    elif "agent" in chunk:
                        for msg in chunk["agent"].get("messages", []):
                            for tc in getattr(msg, "tool_calls", []) or []:
                                yield sse("step", {"tool": tc["name"], "label": texts["steps"].get(tc["name"], "")})
                    elif "tools" in chunk:
                        for card in cards_of(chunk["tools"].get("messages", [])):
                            yield sse("card", card)
                timing_log.info("⏱ answer: total %.3fs", time.perf_counter() - start)
                yield sse("done", {})
            except Exception:  # every model failed, or a bug - the employee gets a calm message
                timing_log.info("⏱ answer: failed after %.3fs", time.perf_counter() - start)
                log.exception("chat failed (thread %s)", thread_id)
                yield sse("error", {"message": texts["overloaded"]})

        return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)

    @r.post("/chat")
    def chat(body: ChatIn):
        return run(body.thread_id or str(uuid.uuid4()), body.message, new=not body.thread_id)

    @r.post("/chat/{thread_id}/rep-answered")
    def rep_answered(thread_id: str = Path(pattern=UUID_RE)):
        if not messages_of(agent, thread_id):
            raise HTTPException(404, "unknown conversation")
        if not rep_queue.take_new_answers(thread_id):  # already handled (another tab, a late reload)
            return StreamingResponse(iter([sse("done", {})]), media_type="text/event-stream", headers=SSE_HEADERS)
        return run(thread_id, texts["repAnswered"], new=False)

    @r.get("/chat/{thread_id}")
    def restore(thread_id: str = Path(pattern=UUID_RE)):
        msgs = messages_of(agent, thread_id)
        if not msgs:
            raise HTTPException(404, "unknown conversation")
        shown = []
        for m in msgs:
            if m.type == "human":
                text = text_of(m.content)
                shown.append({"role": "system" if text == texts["repAnswered"] else "user", "text": text})
            elif m.type == "ai" and text_of(m.content):
                shown.append({"role": "assistant", "text": text_of(m.content)})
        rep = {"pending": len(rep_queue.pending(thread_id)), "new_answers": rep_queue.new_answers(thread_id)}
        return {"thread_id": thread_id, "messages": shown, "cards": cards_of(msgs), "rep": rep}

    @r.get("/conversations/{thread_id}/events")
    async def conversation_changes(request: Request, thread_id: str = Path(pattern=UUID_RE)):
        body = conversation_events(notifier, thread_id, cfg["sseHeartbeatSeconds"], request.is_disconnected)
        return EventStreamResponse(body, media_type="text/event-stream", headers=SSE_HEADERS)

    return r
