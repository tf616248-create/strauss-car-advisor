"""Builds cache/specs-snapshot.json from the live APIs (Ministry of Transport and EEA). Kept in git:
it is what the server uses when an API fails.

    cd backend
    python -m scripts.build_specs_snapshot

Fails loudly if a source fails: a snapshot is never written from another snapshot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.data.loader import load_all
from app.data.specs_store import live_loaders, load_specs_config, now_iso

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = load_all(BACKEND_DIR)
    cfg = load_specs_config(BACKEND_DIR)
    snapshot = {name: {**load(), "fetched_at": now_iso()} for name, load in live_loaders(data.catalog, BACKEND_DIR).items()}
    path = BACKEND_DIR / cfg["snapshot"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    mot, eea = snapshot["mot"], snapshot["eea"]
    print(f"written: {path}")
    print(f"MOT: {len(mot['cars'])}/{len(data.catalog)} found, missing: {mot['missing']}")
    print("MOT rows of other names dropped:",
          {cid: c["otherNamesDropped"] for cid, c in mot["cars"].items() if c["otherNamesDropped"]})
    for cid, c in sorted(eea["cars"].items()):
        print(f"EEA {cid} {data.catalog[cid]['name']}: {c['year']} {'provisional' if c['provisional'] else 'final'}, "
              f"{c['consumptionWhKm']} Wh/km, range {c['rangeKm']} km")
    print(f"EEA missing: {eea['missing']}")


if __name__ == "__main__":
    main()
