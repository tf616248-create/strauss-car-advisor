"""Cache for the car specs (Ministry of Transport and EEA), with a snapshot in git as the fallback.

Loaded in a background thread when the server starts (GET /health is not held up), refreshed every
refreshHours (config/specs.json). A source that fails falls back to cache/specs-snapshot.json, and the
log says which: "mot: נטען מה-API" / "mot: נטען מהגיבוי". Each source carries source, fetched_at and
origin (live / snapshot). The snapshot is made by: python -m scripts.build_specs_snapshot
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode

from app.data import eea_specs, mot_specs

log = logging.getLogger("app.specs")
log.setLevel(logging.INFO)

USER_AGENT = "strauss-car-advisor/specs"


def load_specs_config(backend_dir: Path) -> dict:
    return json.loads((Path(backend_dir) / "config" / "specs.json").read_text(encoding="utf-8"))


def load_car_sources(backend_dir: Path) -> dict:
    return json.loads((Path(backend_dir) / "config" / "car-sources.json").read_text(encoding="utf-8"))["cars"]


def http_get_json(url: str, params: Optional[dict], timeout: float = 60) -> dict:
    full = url + ("?" + urlencode(params) if params else "")
    with urllib.request.urlopen(urllib.request.Request(full, headers={"User-Agent": USER_AGENT}), timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def live_loaders(catalog: dict, backend_dir: Path, get_json: Callable = http_get_json) -> dict[str, Callable[[], dict]]:
    cfg, sources = load_specs_config(backend_dir), load_car_sources(backend_dir)
    mot_get = lambda url, params: get_json(url, params, cfg["mot"]["timeoutSeconds"])  # noqa: E731
    eea_get = lambda url, params: get_json(url, params, cfg["eea"]["timeoutSeconds"])  # noqa: E731
    return {"mot": lambda: mot_specs.load_mot(catalog, cfg, mot_get),
            "eea": lambda: eea_specs.load_eea(sources, cfg, eea_get)}


class SpecsStore:
    def __init__(self, loaders: dict[str, Callable[[], dict]], snapshot_path: Path, refresh_hours: float,
                 clock: Callable[[], float] = time.time, links: Optional[dict[str, str]] = None):
        """links: car id -> importer_url (car-sources.json). It stays even when a source has no data."""
        self._loaders = loaders
        self._links = links or {}
        self._snapshot_path = Path(snapshot_path)
        self._refresh_seconds = refresh_hours * 3600
        self._clock = clock
        self._data: dict[str, Optional[dict]] = {}
        self._loaded_at: Optional[float] = None
        self._lock = threading.Lock()

    def _snapshot(self) -> dict:
        try:
            return json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _load(self, name: str) -> Optional[dict]:
        try:
            entry = {**self._loaders[name](), "origin": "live", "fetched_at": now_iso()}
            log.info("%s: נטען מה-API", name)
            return entry
        except Exception as e:  # noqa: BLE001 - any failure of a source -> the snapshot
            snap = self._snapshot().get(name)
            if snap is None:
                log.error("%s: ה-API נכשל ואין גיבוי (%s: %s)", name, type(e).__name__, e)
                return None
            log.warning("%s: נטען מהגיבוי (%s: %s)", name, type(e).__name__, e)
            return {**snap, "origin": "snapshot"}

    def load_all(self) -> None:
        fresh = {name: self._load(name) for name in self._loaders}
        with self._lock:
            self._data = fresh
            self._loaded_at = self._clock()

    def refresh_if_due(self) -> bool:
        if self._loaded_at is not None and self._clock() - self._loaded_at < self._refresh_seconds:
            return False
        self.load_all()
        return True

    def start_background(self, check_seconds: float = 600) -> threading.Event:
        """Loads now and refreshes when due, in a daemon thread. Returns an event that stops it."""
        stop = threading.Event()

        def run():
            while not stop.is_set():
                try:
                    self.refresh_if_due()
                except Exception:  # noqa: BLE001 - never kill the thread
                    log.exception("specs refresh failed")
                stop.wait(check_seconds)

        threading.Thread(target=run, daemon=True, name="specs-refresh").start()
        return stop

    def for_car(self, car_id: str) -> dict:
        """{"mot": {source, fetched_at, origin, data} | None, "eea": ..., "importer_url": ...}.
        None = no official data (e.g. SANTA FE in the Ministry of Transport). Never touches the net."""
        with self._lock:
            data = dict(self._data)
        out = {}
        for name, entry in data.items():
            car = (entry or {}).get("cars", {}).get(car_id)
            out[name] = None if car is None else {"source": entry["source"], "fetched_at": entry["fetched_at"],
                                                  "origin": entry["origin"], "data": car}
        out["importer_url"] = self._links.get(car_id)
        return out


def build_specs_store(catalog: dict, backend_dir: Path) -> SpecsStore:
    cfg = load_specs_config(backend_dir)
    links = {cid: c.get("importer_url") for cid, c in load_car_sources(backend_dir).items()}
    return SpecsStore(live_loaders(catalog, backend_dir), Path(backend_dir) / cfg["snapshot"], cfg["refreshHours"],
                      links=links)
