"""Live checks against external sites. Not part of the normal run (pytest.ini: -m "not network").

    python -m pytest -m network
"""
import json
import urllib.error
import urllib.request

import pytest

from app.data import eea_specs
from app.data.specs_store import http_get_json, load_specs_config
from tests.conftest import BACKEND_DIR

pytestmark = pytest.mark.network

SOURCES = json.loads((BACKEND_DIR / "config" / "car-sources.json").read_text(encoding="utf-8"))["cars"]
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126 Safari/537.36", "Accept": "text/html"}


@pytest.mark.parametrize("car_id", sorted(c for c, s in SOURCES.items() if not s.get("checked_manually")))
def test_importer_page_opens(car_id):
    """Pages marked checked_manually (tesla.com answers 403 to bots) are skipped."""
    url = SOURCES[car_id]["importer_url"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER), timeout=30) as res:
            status = res.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 200, f"{SOURCES[car_id]['name']}: {status} {url}"


@pytest.mark.parametrize("car_id", sorted(c for c, s in SOURCES.items() if s.get("eea")))
def test_eea_key_returns_rows(car_id):
    """In one of the tables (2022-2025, final or provisional)."""
    cfg = load_specs_config(BACKEND_DIR)["eea"]
    spec = eea_specs.find_car(SOURCES[car_id]["eea"], cfg["exclude"].get(car_id, []), cfg, http_get_json)
    assert spec is not None, f"{SOURCES[car_id]['name']}: no EEA rows in 2022-2025"
