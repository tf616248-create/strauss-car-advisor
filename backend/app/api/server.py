"""Runs the API with settings from backend/.env.

    cd backend
    .venv/Scripts/python -m uvicorn app.api.server:app --reload --port 8000

With DATABASE_URL (Neon): the rep queue and the conversations (PostgresSaver) are in Postgres.
Without it: everything is in memory (tests, local development).
One worker only: the list of open SSE connections lives in this process (see render.yaml).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from app.agent.advisor import load_agent_config
from app.agent.models import build_model
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.data.loader import load_all

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

# timing lines (app/timing.py) in the console, next to uvicorn's own
_timing_handler = logging.StreamHandler()
_timing_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
logging.getLogger("app.timing").addHandler(_timing_handler)
logging.getLogger("app.timing").propagate = False

origins = tuple(o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o.strip())

cfg = load_agent_config(BACKEND_DIR)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    from app.db import PostgresRepQueue, make_checkpointer, make_pool

    pool = make_pool(database_url)
    rep_queue = PostgresRepQueue(pool)
    rep_queue.setup()
    checkpointer = make_checkpointer(pool)
else:
    rep_queue, checkpointer = InMemoryRepQueue(), None

app = create_app(
    data=load_all(BACKEND_DIR),
    model=build_model(cfg["modelTimeoutSeconds"], thinking_level=cfg["geminiThinkingLevel"]),
    rep_queue=rep_queue,
    notifier=InMemoryNotifier(),
    cfg=cfg,
    rep_passcode=os.environ.get("REP_PASSCODE") or None,
    checkpointer=checkpointer,
    origins=origins,
)
