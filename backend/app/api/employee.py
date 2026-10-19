"""Employee routes (the chat screen, /).

  POST /login                      {code} -> {token}: a demo code -> a JWT (app/auth.py)
  GET  /threads                    the logged-in employee's conversations, newest first
  POST /chat                       SSE: thread, step, token, card, done | error
  POST /chat/{thread_id}/rep-answered   SSE: new rep answers - rerun with the system note (once per answer)
  GET  /chat/{thread_id}           the conversation's current state: messages, cards, rep status
  GET  /conversations/{thread_id}/events   SSE: "changed" (no data) + a heartbeat comment

Every route except /login needs the employee's token ("Authorization: Bearer ..."; the events
stream takes ?token=, since EventSource can't send headers). A conversation belongs to the
employee who started it (app/threads.py); anyone else's is 404, not 403, so a guessed id says
nothing. No codes configured (EMPLOYEE_CODES) = the employee screen is closed (503).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from pydantic import BaseModel, Field

from app.agent.models import ModelStalledError
from app.api.common import (SSE_HEADERS, UUID_RE, EventStreamResponse, cards_of, messages_of, sse,
                            text_of, thread_config, title_of)
from app.api.events import conversation_events
from app.auth import LoginLimiter
from app.usage import append_row, turn_usage

log = logging.getLogger(__name__)
timing_log = logging.getLogger("app.timing")


class LoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: Optional[str] = Field(default=None, pattern=UUID_RE)


def router(*, agent, rep_queue, notifier, cfg: dict, threads, auth=None, usage_file=None) -> APIRouter:
    """auth: app/auth.EmployeeAuth, or None = closed. threads: who owns which conversation."""
    texts = cfg["texts"]
    prices = cfg["usage"]["prices"]
    limiter = LoginLimiter(cfg["auth"]["maxFailedLogins"], cfg["auth"]["failedLoginWindowSeconds"])

    def employee_of(token: str) -> str:
        if auth is None:
            raise HTTPException(503, "employee login is not configured")
        employee = auth.verify(token)
        if not employee:
            raise HTTPException(401, "login needed")
        return employee

    def bearer(authorization: Optional[str]) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        return token.strip() if scheme.lower() == "bearer" else ""

    def current_employee(authorization: Optional[str] = Header(default=None)) -> str:
        return employee_of(bearer(authorization))

    def own(thread_id: str, employee: str) -> None:
        if threads.owner(thread_id) != employee:
            raise HTTPException(404, "unknown conversation")

    def record_usage(thread_id: str, question: str, answers: list) -> None:
        """Cost of the question: one line in the server log, and a row in usage_file."""
        u = turn_usage(answers, prices)
        cost = "-" if u["cost_usd"] is None else f"${u['cost_usd']:.5f}"
        timing_log.info("💲 question: %d model calls, %d tokens in, %d out (%s), %s",
                        u["calls"], u["input_tokens"], u["output_tokens"], u["models"], cost)
        if usage_file is not None:
            try:
                append_row(usage_file, {**u, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "question": question, "thread_id": thread_id})
            except OSError:  # e.g. the file is open in Excel - the answer matters more than the row
                log.exception("could not write %s", usage_file)
    r = APIRouter(tags=["employee"])

    def run(thread_id: str, message: str, new: bool) -> StreamingResponse:
        def stream():
            if new:
                yield sse("thread", {"thread_id": thread_id})
            start = time.perf_counter()
            first_token = None
            answers = []  # the model's messages in this question, for its cost
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
                        answers.extend(chunk["agent"].get("messages", []))
                        for msg in chunk["agent"].get("messages", []):
                            for tc in getattr(msg, "tool_calls", []) or []:
                                yield sse("step", {"tool": tc["name"], "label": texts["steps"].get(tc["name"], "")})
                    elif "tools" in chunk:
                        for card in cards_of(chunk["tools"].get("messages", [])):
                            yield sse("card", card)
                timing_log.info("⏱ answer: total %.3fs", time.perf_counter() - start)
                yield sse("done", {})
            except (Exception, ModelStalledError):  # every model failed, one went silent, or a bug -
                # the employee gets a calm message
                timing_log.info("⏱ answer: failed after %.3fs", time.perf_counter() - start)
                log.exception("chat failed (thread %s)", thread_id)
                yield sse("error", {"message": texts["overloaded"]})
            finally:
                if answers:
                    record_usage(thread_id, message, answers)
                try:  # the history list: a title and to the top
                    threads.touch(thread_id, title_of(messages_of(agent, thread_id), texts["repAnswered"]))
                except Exception:  # the answer matters more than the list
                    log.exception("could not update the history (thread %s)", thread_id)

        return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)

    @r.post("/login")
    def login(body: LoginIn, request: Request):
        if auth is None:
            raise HTTPException(503, "employee login is not configured")
        key = request.client.host if request.client else "unknown"
        if not limiter.allowed(key):
            raise HTTPException(429, "too many wrong codes, try again later")
        employee = auth.login(body.code)
        if not employee:
            limiter.failed(key)
            raise HTTPException(401, "wrong code")
        return {"token": auth.issue(employee), "employee_id": employee}

    @r.get("/threads")
    def my_threads(employee: str = Depends(current_employee)):
        return {"threads": threads.list(employee)}

    @r.post("/chat")
    def chat(body: ChatIn, employee: str = Depends(current_employee)):
        if body.thread_id:
            own(body.thread_id, employee)
            return run(body.thread_id, body.message, new=False)
        thread_id = str(uuid.uuid4())
        threads.add(employee, thread_id)
        return run(thread_id, body.message, new=True)

    @r.post("/chat/{thread_id}/rep-answered")
    def rep_answered(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
        if not messages_of(agent, thread_id):
            raise HTTPException(404, "unknown conversation")
        if not rep_queue.take_new_answers(thread_id):  # already handled (another tab, a late reload)
            return StreamingResponse(iter([sse("done", {})]), media_type="text/event-stream", headers=SSE_HEADERS)
        return run(thread_id, texts["repAnswered"], new=False)

    @r.get("/chat/{thread_id}")
    def restore(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
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
    def conversation_changes(request: Request, thread_id: str = Path(pattern=UUID_RE),
                             token: str = Query(default=""), authorization: Optional[str] = Header(default=None)):
        own(thread_id, employee_of(bearer(authorization) or token))
        body = conversation_events(notifier, thread_id, cfg["sseHeartbeatSeconds"], request.is_disconnected)
        return EventStreamResponse(body, media_type="text/event-stream", headers=SSE_HEADERS)

    return r
