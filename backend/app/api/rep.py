"""Rep routes (the transport rep's screen, /rep). All behind the shared passcode (REP_PASSCODE),
set once on the router so a new rep route cannot be left open. Real login is a pilot item.

  GET  /rep/requests               open questions (+ the employee's card)
  POST /rep/requests/{id}/answer   saved first, then the conversation rings
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.common import cards_of, messages_of

log = logging.getLogger(__name__)


class AnswerIn(BaseModel):
    values: dict[str, str | int | float]


def router(*, agent, rep_queue, notifier, rep_passcode: Optional[str]) -> APIRouter:
    def require_rep(x_rep_passcode: Optional[str] = Header(default=None)) -> None:
        if not rep_passcode:
            raise HTTPException(503, "rep screen is not configured (REP_PASSCODE)")
        if not x_rep_passcode or not secrets.compare_digest(x_rep_passcode, rep_passcode):
            raise HTTPException(401, "wrong passcode")

    r = APIRouter(prefix="/rep", tags=["rep"], dependencies=[Depends(require_rep)])

    @r.get("/requests")
    def rep_requests():
        out = []
        for req in rep_queue.all_pending():
            cards = cards_of(messages_of(agent, req["thread_id"]))
            out.append({"id": req["id"], "thread_id": req["thread_id"], "fields": req["fields"],
                        "question": req["question"], "car_key": req["car_key"],
                        "card": cards[-1]["card"] if cards else None})
        return out

    @r.post("/requests/{request_id}/answer")
    def rep_answer(request_id: str, body: AnswerIn):
        req = rep_queue.get(request_id)
        if req is None:
            raise HTTPException(404, "unknown request")
        try:
            rep_queue.answer(request_id, body.values)
        except Exception:  # not saved - so nobody is told it changed
            log.exception("saving rep answer %s failed", request_id)
            raise HTTPException(503, "the answer was not saved, try again")
        notifier.publish(req["thread_id"])
        return {"status": "ok"}

    return r
