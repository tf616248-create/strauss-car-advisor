"""Settings read from the environment at startup."""
from __future__ import annotations

from typing import Mapping

LOCAL_FRONTEND = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins(env: Mapping[str, str]) -> list[str]:
    """Only the frontend (FRONTEND_ORIGIN, e.g. the Netlify domain). Off Render (development),
    the local Vite server too. Render sets RENDER=true in every service."""
    origins = []
    if env.get("FRONTEND_ORIGIN"):
        origins.append(env["FRONTEND_ORIGIN"].strip().rstrip("/"))
    if not env.get("RENDER"):
        origins += [o for o in LOCAL_FRONTEND if o not in origins]
    return origins
