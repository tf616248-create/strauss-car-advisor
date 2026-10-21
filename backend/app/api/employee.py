"""Employee routes (the chat screen, /).

  POST /login                      {code} -> {token}: a demo code -> a JWT (app/auth.py)
  GET  /me                         the logged-in employee: {employee_id, name} (app/employees.py)
  GET  /profile                    the employee's profile: {employee_id, fields, group} (group: read only,
                                   from the occupation; app/profile.py)
  PATCH /profile                   {fields}: update some fields (null clears one); 422 {invalid} - nothing kept
  GET  /threads                    the logged-in employee's conversations, newest first
  POST /chat                       SSE: thread, step, token, card, done | error
  POST /chat/{thread_id}/rep-answered   SSE: new rep answers - rerun with the system note (once per answer)
  GET  /chat/{thread_id}           the conversation's current state: messages, cards, rep status, payslip
  DELETE /chat/{thread_id}         deletes the conversation, its payslip with it
  POST /chat/{thread_id}/payslip   SSE: a payslip file (JPG/PNG/PDF as the raw body), read once; then the bot
                                   carries on with the values: step, payslip, token, card, done | error
  POST /chat/{thread_id}/payslip-text   SSE: the same, from text pasted from a payslip
  GET  /chat/{thread_id}/payslip   the stored payslip image (JPEG)
  GET  /conversations/{thread_id}/events   SSE: "changed" (no data) + a heartbeat comment

Every route except /login needs the employee's token ("Authorization: Bearer ..."; the events
stream takes ?token=, since EventSource can't send headers). A conversation belongs to the
employee who started it (app/threads.py); anyone else's is 404, not 403, so a guessed id says
nothing. No codes configured (EMPLOYEE_CODES) = the employee screen is closed (503).
Every run of the agent gets the employee id, so the tools fill in the employee's profile, in code.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk
from pydantic import BaseModel, Field

from app import payslip as payslip_mod
from app import profile as profile_mod
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


class ProfileIn(BaseModel):
    fields: dict


class PayslipTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


PAYSLIP_HTTP = {"too_large": 413, "bad_type": 415, "unreadable": 422}


def router(*, agent, rep_queue, notifier, cfg: dict, threads, payslips, payslip_reader, employees, profiles,
           occupations: dict, auth=None, usage_file=None) -> APIRouter:
    """auth: app/auth.EmployeeAuth, or None = closed. threads: who owns which conversation.
    payslips: the payslip kept with each conversation (app/payslip.py, app/db.py).
    employees: login id -> name, for GET /me (app/employees.py, app/db.py).
    profiles: each employee's profile (app/profile.py, app/db.py); occupations: the sheet, for the group."""
    matcher = profile_mod.OccupationMatcher(occupations, cfg["profile"]["maxSuggestions"])
    texts = cfg["texts"]
    ptexts = texts["payslip"]
    max_bytes = cfg["payslip"]["maxBytes"]
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

    def touch(thread_id: str) -> None:
        try:  # the history list: a title and to the top
            threads.touch(thread_id, title_of(messages_of(agent, thread_id), texts["repAnswered"]))
        except Exception:  # the answer matters more than the list
            log.exception("could not update the history (thread %s)", thread_id)

    def profile_view(employee: str) -> dict:
        fields = profiles.get(employee)
        return {"employee_id": employee, "fields": fields, "group": profile_mod.group_of(fields, occupations)}

    def update_profile(employee: str, values: dict) -> list[str]:
        """Keeps the values that differ from the profile; returns their fields. LangSmith: the names only."""
        current = profiles.get(employee)
        changed = {k: v for k, v in values.items() if current.get(k) != v}
        if changed:
            profiles.update(employee, changed)
            profile_mod.trace_profile("profile_updated", sorted(changed))
        return sorted(changed)

    def answer(thread_id: str, message, question: str, employee: str, new: bool = False, extra_answers=()):
        """The bot's answer as SSE events. message: the employee's text, or a ready message (a system note)."""
        if new:
            yield sse("thread", {"thread_id": thread_id})
        start = time.perf_counter()
        first_token = None
        answers = list(extra_answers)  # the model's messages in this question, for its cost
        item = ("user", message) if isinstance(message, str) else message
        try:
            for mode, chunk in agent.stream({"messages": [item]}, thread_config(thread_id, employee),
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
                record_usage(thread_id, question, answers)
            touch(thread_id)

    def run(thread_id: str, message: str, new: bool, employee: str) -> StreamingResponse:
        return StreamingResponse(answer(thread_id, message, message, employee, new), media_type="text/event-stream",
                                 headers=SSE_HEADERS)

    def read_payslip(thread_id: str, kind: str, read, employee: str) -> StreamingResponse:
        """Reads the payslip (the model sees it once), keeps the values, and the bot carries on with them -
        no confirmation from the employee. Unreadable: the fixed message, and the questions go on."""
        def stream():
            yield sse("step", {"tool": "payslip", "label": texts["steps"]["payslip"]})
            reading = read()
            payslip_mod.trace_upload(thread_id, kind, reading.status, sorted(reading.fields))
            changed = []
            if reading.status == "ok":
                try:  # the payslip's values go to the profile too: the latest value wins
                    clean, _ = profile_mod.validate(reading.fields, cfg, matcher)
                    changed = update_profile(employee, clean)
                except Exception:  # noqa: BLE001 - the values are in the conversation all the same
                    log.exception("could not update the profile from the payslip (thread %s)", thread_id)
            note = payslip_mod.note(reading.fields, reading.status, cfg, source=kind, profile_updated=bool(changed))
            if reading.status == "ok":
                try:
                    payslips.set_fields(thread_id, reading.fields)
                except Exception:  # noqa: BLE001 - the values are in the conversation all the same
                    log.exception("could not keep the payslip's fields (thread %s)", thread_id)
                yield sse("payslip", {"status": reading.status, "fields": reading.fields})
                yield from answer(thread_id, note, "[payslip]", employee, extra_answers=reading.answers)
                return
            yield sse("payslip", {"status": reading.status, "fields": reading.fields})
            text = ptexts["noVision" if reading.status == "no_vision" else "failed"]
            try:
                # no model call: the note and the fixed message go into the conversation as they are
                agent.update_state(thread_config(thread_id), {"messages": [note, AIMessage(content=text)]},
                                   as_node="agent")
                yield sse("token", {"text": text})
                yield sse("done", {})
            except Exception:  # noqa: BLE001 - e.g. the database is down: a calm message
                log.exception("payslip failed (thread %s)", thread_id)
                yield sse("error", {"message": texts["overloaded"]})
            if reading.answers:
                record_usage(thread_id, "[payslip]", reading.answers)
            touch(thread_id)

        return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)

    async def body_capped(request: Request) -> bytes:
        """The upload, refused as soon as it passes maxBytes (not after reading all of it)."""
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise HTTPException(413, ptexts["tooLarge"])
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(413, ptexts["tooLarge"])
            chunks.append(chunk)
        return b"".join(chunks)

    def payslip_view(thread_id: str) -> Optional[dict]:
        row = payslips.get(thread_id)
        if row is None:
            return None
        return {"source": row["source"], "fields": row["fields"],
                "image": f"/chat/{thread_id}/payslip" if row["image"] is not None else None}

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

    @r.get("/me")
    def me(employee: str = Depends(current_employee)):
        return {"employee_id": employee, "name": employees.name(employee)}

    @r.get("/profile")
    def read_profile(employee: str = Depends(current_employee)):
        view = profile_view(employee)
        profile_mod.trace_profile("profile_read", sorted(view["fields"]))
        return view

    @r.patch("/profile")
    def write_profile(body: ProfileIn, employee: str = Depends(current_employee)):
        """All or nothing: one bad value and nothing is kept (the page shows what to fix)."""
        clean, bad = profile_mod.validate(body.fields, cfg, matcher)
        if bad:
            raise HTTPException(422, {"invalid": bad})
        update_profile(employee, clean)
        return profile_view(employee)

    @r.get("/threads")
    def my_threads(employee: str = Depends(current_employee)):
        return {"threads": threads.list(employee)}

    @r.post("/chat")
    def chat(body: ChatIn, employee: str = Depends(current_employee)):
        if body.thread_id:
            own(body.thread_id, employee)
            return run(body.thread_id, body.message, False, employee)
        thread_id = str(uuid.uuid4())
        threads.add(employee, thread_id)
        return run(thread_id, body.message, True, employee)

    @r.post("/chat/{thread_id}/rep-answered")
    def rep_answered(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
        if not messages_of(agent, thread_id):
            raise HTTPException(404, "unknown conversation")
        if not rep_queue.take_new_answers(thread_id):  # already handled (another tab, a late reload)
            return StreamingResponse(iter([sse("done", {})]), media_type="text/event-stream", headers=SSE_HEADERS)
        return run(thread_id, texts["repAnswered"], False, employee)

    @r.get("/chat/{thread_id}")
    def restore(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
        msgs = messages_of(agent, thread_id)
        if not msgs:
            raise HTTPException(404, "unknown conversation")
        shown = []
        for m in msgs:
            if payslip_mod.is_note(m):
                source = m.additional_kwargs[payslip_mod.NOTE_KEY].get("source")
                shown.append({"role": "payslip", "text": ptexts["shownText" if source == "text" else "shown"]})
            elif m.type == "human":
                text = text_of(m.content)
                shown.append({"role": "system" if text == texts["repAnswered"] else "user", "text": text})
            elif m.type == "ai" and text_of(m.content):
                shown.append({"role": "assistant", "text": text_of(m.content)})
        rep = {"pending": len(rep_queue.pending(thread_id)), "new_answers": rep_queue.new_answers(thread_id)}
        return {"thread_id": thread_id, "messages": shown, "cards": cards_of(msgs), "rep": rep,
                "payslip": payslip_view(thread_id)}

    @r.delete("/chat/{thread_id}", status_code=204)
    def delete(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
        threads.delete(thread_id)
        payslips.delete(thread_id)  # in Postgres the line above already did it (on delete cascade)
        agent.checkpointer.delete_thread(thread_id)
        return Response(status_code=204)

    @r.post("/chat/{thread_id}/payslip")
    async def upload_payslip(request: Request, thread_id: str = Path(pattern=UUID_RE),
                             employee: str = Depends(current_employee)):
        """The raw file as the body (fetch(url, {body: file})): recognised by its bytes, not its Content-Type."""
        await run_in_threadpool(own, thread_id, employee)
        raw = await body_capped(request)
        try:
            prepared = await run_in_threadpool(payslip_mod.prepare, raw, cfg["payslip"])
        except payslip_mod.PayslipError as e:
            raise HTTPException(PAYSLIP_HTTP[e.code], ptexts[e.text_key]) from None
        await run_in_threadpool(payslips.save, thread_id, prepared.stored, "image")
        return read_payslip(thread_id, "image", lambda: payslip_reader.read_image(prepared.for_model), employee)

    @r.post("/chat/{thread_id}/payslip-text")
    def paste_payslip(body: PayslipTextIn, thread_id: str = Path(pattern=UUID_RE),
                      employee: str = Depends(current_employee)):
        own(thread_id, employee)
        payslips.save(thread_id, None, "text")  # the values only: the pasted text itself is not kept
        return read_payslip(thread_id, "text", lambda: payslip_reader.read_text(body.text), employee)

    @r.get("/chat/{thread_id}/payslip")
    def payslip_image(thread_id: str = Path(pattern=UUID_RE), employee: str = Depends(current_employee)):
        own(thread_id, employee)
        row = payslips.get(thread_id)
        if row is None or row["image"] is None:
            raise HTTPException(404, "no payslip")
        return Response(content=row["image"], media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @r.get("/conversations/{thread_id}/events")
    def conversation_changes(request: Request, thread_id: str = Path(pattern=UUID_RE),
                             token: str = Query(default=""), authorization: Optional[str] = Header(default=None)):
        own(thread_id, employee_of(bearer(authorization) or token))
        body = conversation_events(notifier, thread_id, cfg["sseHeartbeatSeconds"], request.is_disconnected)
        return EventStreamResponse(body, media_type="text/event-stream", headers=SSE_HEADERS)

    return r
