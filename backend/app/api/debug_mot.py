"""TEMPORARY: can the server reach the Ministry of Transport API on data.gov.il?

GET /debug/mot-check - one request (limit=1), 15s timeout. Delete after the check.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from fastapi import APIRouter

MOT_URL = ("https://data.gov.il/api/3/action/datastore_search"
           "?resource_id=142afde2-6228-49f9-8a29-9b6c3a0cbe40&limit=1")
TIMEOUT_SECONDS = 15

router = APIRouter()


@router.get("/debug/mot-check")
def mot_check():
    start = time.perf_counter()
    elapsed = lambda: round((time.perf_counter() - start) * 1000)  # noqa: E731
    try:
        req = urllib.request.Request(MOT_URL, headers={"User-Agent": "strauss-car-advisor/mot-check"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as res:
            status = res.status
            body = json.loads(res.read().decode("utf-8"))
        result = body.get("result") or {}
        return {"ok": True, "status_code": status, "elapsed_ms": elapsed(), "success": body.get("success"),
                "fields": [f.get("id") for f in result.get("fields", [])]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "http", "status_code": e.code, "elapsed_ms": elapsed()}
    except (TimeoutError, socket.timeout):
        return {"ok": False, "error": "timeout", "status_code": None, "elapsed_ms": elapsed()}
    except urllib.error.URLError as e:
        kind = "timeout" if isinstance(e.reason, (TimeoutError, socket.timeout)) else "connection"
        return {"ok": False, "error": kind, "detail": str(e.reason), "status_code": None, "elapsed_ms": elapsed()}
    except ValueError as e:  # not JSON
        return {"ok": False, "error": "bad_json", "detail": str(e)[:200], "status_code": None, "elapsed_ms": elapsed()}
