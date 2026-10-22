"""Ready to go live: Render settings, CORS, startup that is safe to repeat, data files in Git."""
import codecs
import subprocess

import yaml

from app.agent.models import available_models
from app.api.settings import cors_origins
from tests.conftest import BACKEND_DIR

ROOT = BACKEND_DIR.parent
LOCAL = {"http://localhost:5173", "http://127.0.0.1:5173",
         "http://localhost:8081", "http://127.0.0.1:8081"}  # Vite, and the phone app in a browser (Expo web)


# --- render.yaml ------------------------------------------------------------------


def service():
    [svc] = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))["services"]
    return svc


def test_render_service_settings():
    svc = service()
    assert svc["type"] == "web"
    assert svc["runtime"] == "python"
    assert svc["rootDir"] == "backend"
    assert svc["region"] == "frankfurt"
    assert svc["plan"] == "free"
    assert svc["buildCommand"] == "pip install -r requirements.txt"
    assert svc["healthCheckPath"] == "/health"


def test_render_runs_one_worker_of_the_real_app():
    start = service()["startCommand"]
    assert "--workers 1" in start
    assert "--port $PORT" in start and "--host 0.0.0.0" in start
    module = start.split()[1].split(":")[0]  # e.g. app.api.server
    assert (BACKEND_DIR / (module.replace(".", "/") + ".py")).exists()


def test_render_secrets_are_names_only():
    env = {e["key"]: e for e in service()["envVars"]}
    for key in ["DATABASE_URL", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "FRONTEND_ORIGIN",
                "REP_PASSCODE"]:
        assert env[key] == {"key": key, "sync": False}, key


def test_python_version_matches_the_tests():
    import sys

    pinned = (BACKEND_DIR / ".python-version").read_text().strip()
    assert pinned == f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    assert {"key": "PYTHON_VERSION", "value": pinned} in service()["envVars"]


# --- CORS -------------------------------------------------------------------------


def test_cors_on_render_is_only_the_frontend():
    assert cors_origins({"RENDER": "true", "FRONTEND_ORIGIN": "https://advisor.netlify.app/"}) == ["https://advisor.netlify.app"]


def test_cors_in_development_adds_localhost():
    assert set(cors_origins({"FRONTEND_ORIGIN": "https://advisor.netlify.app"})) == {"https://advisor.netlify.app"} | LOCAL
    assert set(cors_origins({})) == LOCAL


def test_cors_on_render_without_frontend_allows_nothing():
    assert cors_origins({"RENDER": "true"}) == []


# --- model key name on Render -----------------------------------------------------


def test_gemini_api_key_is_read():
    assert [name for name, _ in available_models({"GEMINI_API_KEY": "g"})] == ["gemini"]


# --- data files -------------------------------------------------------------------


def test_data_files_are_in_git_and_not_ignored():
    tracked = subprocess.run(["git", "ls-files", "backend/data"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for name in ["strauss-rules.json", "strauss-data.xlsx", "vehicle-values-2026.csv"]:
        path = f"backend/data/{name}"
        assert path in tracked, path
        ignored = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0
        assert not ignored, path


def test_csv_is_read_with_a_codec_that_exists_everywhere():
    """windows-1255 is built into Python on every OS, and the loader asks for it explicitly."""
    assert codecs.lookup("windows-1255").name == "cp1255"
    raw = (BACKEND_DIR / "data" / "vehicle-values-2026.csv").read_bytes()[:4000]
    text = raw.decode("windows-1255")
    assert any("֐" <= ch <= "׿" for ch in text)  # Hebrew header decoded, not mojibake
