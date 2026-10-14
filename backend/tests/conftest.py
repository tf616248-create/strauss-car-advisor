from pathlib import Path

import pytest

from app.data.loader import load_all

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def data():
    return load_all(BACKEND_DIR)
