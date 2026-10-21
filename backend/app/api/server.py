"""Runs the API with settings from backend/.env.

    cd backend
    .venv/Scripts/python -m uvicorn app.api.server:app --reload --port 8000

With DATABASE_URL (Neon): the rep queue and the conversations (PostgresSaver) are in Postgres.
Without it: everything is in memory (tests, local development).
One worker only: the list of open SSE connections lives in this process (see render.yaml).
Tables and PostgresSaver are set up at startup; both are safe to run on every restart.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from app import tracing
from app.agent.advisor import load_agent_config
from app.agent.models import build_model, build_vision_model
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.api.settings import cors_origins
from app.auth import EmployeeAuth
from app.data.loader import load_all
from app.employees import load_seed
from app.data.specs_store import build_specs_store
from app.payslip import PayslipReader

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

# timing lines (app/timing.py) in the console, next to uvicorn's own
_timing_handler = logging.StreamHandler()
_timing_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
logging.getLogger("app.timing").addHandler(_timing_handler)
logging.getLogger("app.timing").propagate = False
# car specs: "נטען מה-API" / "נטען מהגיבוי" (app/data/specs_store.py)
logging.getLogger("app.specs").addHandler(_timing_handler)
logging.getLogger("app.specs").propagate = False
# LangSmith: on only with LANGSMITH_TRACING + LANGSMITH_API_KEY (app/tracing.py)
logging.getLogger("app.tracing").addHandler(_timing_handler)
logging.getLogger("app.tracing").setLevel(logging.INFO)
logging.getLogger("app.tracing").propagate = False
tracing.configure(os.environ)

origins = tuple(cors_origins(os.environ))

cfg = load_agent_config(BACKEND_DIR)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    from app.db import (PostgresEmployees, PostgresPayslips, PostgresProfiles, PostgresRepQueue, PostgresThreads,
                        make_checkpointer, make_pool)

    pool = make_pool(database_url)
    rep_queue = PostgresRepQueue(pool)
    rep_queue.setup()
    threads = PostgresThreads(pool)
    threads.setup()
    payslips = PostgresPayslips(pool)
    payslips.setup()  # after employee_threads: a payslip belongs to a conversation
    employees = PostgresEmployees(pool, load_seed(BACKEND_DIR))  # dummy names, added when missing
    employees.setup()
    profiles = PostgresProfiles(pool)  # after employees: a profile belongs to an employee
    profiles.setup()
    checkpointer = make_checkpointer(pool)
else:
    # None: create_app keeps them in memory
    rep_queue, checkpointer, threads, payslips, employees, profiles = InMemoryRepQueue(), None, None, None, None, None

data = load_all(BACKEND_DIR)

# car specs (MOT + EEA) for car_specs and rank_options: starts from the snapshot, then loads from the
# APIs in a background thread, so /health is not held up; refreshed daily
specs = build_specs_store(data.catalog, BACKEND_DIR)

model = build_model(cfg["modelTimeoutSeconds"], thinking_level=cfg["geminiThinkingLevel"])
# a payslip photo: only the models that read images (payslip.visionModels); pasted text: any model
vision = build_vision_model(cfg["modelTimeoutSeconds"], cfg["payslip"]["visionModels"],
                            thinking_level=cfg["geminiThinkingLevel"])

app = create_app(
    data=data,
    model=model,
    rep_queue=rep_queue,
    notifier=InMemoryNotifier(),
    cfg=cfg,
    rep_passcode=os.environ.get("REP_PASSCODE") or None,
    # employee login: EMPLOYEE_CODES + JWT_SECRET (app/auth.py); no codes = the employee screen is closed
    employee_auth=EmployeeAuth.from_env(os.environ, hours=cfg["auth"]["tokenHours"]),
    threads=threads,
    payslips=payslips,
    employees=employees,
    profiles=profiles,
    payslip_reader=PayslipReader(vision, model, cfg),
    checkpointer=checkpointer,
    origins=origins,
    usage_file=BACKEND_DIR / cfg["usage"]["file"],  # cost of each question, not in git
    specs=specs,
)
app.state.specs = specs
specs.start_background()
