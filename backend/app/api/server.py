"""Runs the API with settings from backend/.env.

    cd backend
    .venv/Scripts/python -m uvicorn app.api.server:app --reload --port 8000

Rep queue and checkpoints are in memory until Supabase is connected.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from app.agent.advisor import load_agent_config
from app.agent.models import build_model
from app.agent.rep_queue import InMemoryRepQueue
from app.api.main import InMemoryNotifier, create_app
from app.data.loader import load_all

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

origins = tuple(o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o.strip())

app = create_app(
    data=load_all(BACKEND_DIR),
    model=build_model(),
    rep_queue=InMemoryRepQueue(),
    notifier=InMemoryNotifier(),
    cfg=load_agent_config(BACKEND_DIR),
    rep_passcode=os.environ.get("REP_PASSCODE") or None,
    origins=origins,
)
