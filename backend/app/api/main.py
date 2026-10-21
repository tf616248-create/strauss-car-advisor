"""HTTP API: builds the agent and puts the two sides together.

  app/api/employee.py   the employee's chat screen (/chat..., /conversations/.../events)
  app/api/rep.py        the rep's screen (/rep/...), all behind the passcode
  GET /health           here; does not touch the database (Neon may sleep)

The database is the source of truth; the events stream only rings, and the browser
reads the state again (GET /chat/{id}).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_agent
from app.api import employee, rep
from app.employees import InMemoryEmployees, load_seed
from app.payslip import InMemoryPayslips, PayslipReader
from app.profile import InMemoryProfiles
from app.usage_limit import InMemoryUsage, UsageMeter
from app.threads import InMemoryThreads

BACKEND_DIR = Path(__file__).resolve().parents[2]


def create_app(*, data, model, rep_queue, notifier, cfg: dict, rep_passcode: Optional[str],
               checkpointer=None, origins: tuple[str, ...] = ("http://localhost:5173",),
               usage_file=None, specs=None, employee_auth=None, threads=None, payslips=None,
               payslip_reader=None, employees=None, profiles=None, usage=None) -> FastAPI:
    """usage_file: a CSV with the cost of each question (app/usage.py); None writes nothing (tests).
    specs: the car specs store (app/data/specs_store.py); None = the snapshot in git, no network.
    employee_auth: app/auth.EmployeeAuth; None = the employee screen is closed (no EMPLOYEE_CODES).
    threads: who owns which conversation (app/threads.py, app/db.py); None = in memory.
    payslips: the payslip kept with each conversation (app/payslip.py, app/db.py); None = in memory.
    payslip_reader: app/payslip.PayslipReader; None = no model that reads images, pasted text with `model`.
    employees: login id -> name (app/employees.py, app/db.py); None = in memory, from config/employees.json.
    profiles: each employee's profile (app/profile.py, app/db.py); None = in memory.
    usage: the weekly token count per employee (app/usage_limit.py, app/db.py); None = in memory."""
    profiles = profiles if profiles is not None else InMemoryProfiles(cfg["settings"]["defaults"])
    employees = employees if employees is not None else InMemoryEmployees(load_seed(BACKEND_DIR))
    agent = build_agent(model, data, rep_queue, cfg, checkpointer, specs=specs, profiles=profiles, employees=employees)
    app = FastAPI(title="Strauss car advisor")
    app.state.agent = agent
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(employee.router(agent=agent, rep_queue=rep_queue, notifier=notifier, cfg=cfg,
                                        usage_file=usage_file, auth=employee_auth,
                                        threads=threads if threads is not None else InMemoryThreads(),
                                        payslips=payslips if payslips is not None else InMemoryPayslips(),
                                        payslip_reader=payslip_reader or PayslipReader(None, model, cfg),
                                        employees=employees,
                                        profiles=profiles, occupations=data.occupations,
                                        meter=UsageMeter(usage if usage is not None else InMemoryUsage(), cfg)))
    app.include_router(rep.router(agent=agent, rep_queue=rep_queue, notifier=notifier, rep_passcode=rep_passcode))
    return app
