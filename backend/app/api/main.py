"""HTTP API: builds the agent and puts the two sides together.

  app/api/employee.py   the employee's chat screen (/chat..., /conversations/.../events)
  app/api/rep.py        the rep's screen (/rep/...), all behind the passcode
  GET /health           here; does not touch the database (Neon may sleep)

The database is the source of truth; the events stream only rings, and the browser
reads the state again (GET /chat/{id}).
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_agent
from app.api import employee, rep


def create_app(*, data, model, rep_queue, notifier, cfg: dict, rep_passcode: Optional[str],
               checkpointer=None, origins: tuple[str, ...] = ("http://localhost:5173",),
               usage_file=None, specs=None) -> FastAPI:
    """usage_file: a CSV with the cost of each question (app/usage.py); None writes nothing (tests).
    specs: the car specs store (app/data/specs_store.py); None = the snapshot in git, no network."""
    agent = build_agent(model, data, rep_queue, cfg, checkpointer, specs=specs)
    app = FastAPI(title="Strauss car advisor")
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(employee.router(agent=agent, rep_queue=rep_queue, notifier=notifier, cfg=cfg,
                                        usage_file=usage_file))
    app.include_router(rep.router(agent=agent, rep_queue=rep_queue, notifier=notifier, rep_passcode=rep_passcode))
    return app
