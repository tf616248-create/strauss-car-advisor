"""Employee login for tests: two demo codes and a client that is already logged in."""
from fastapi.testclient import TestClient

from app.auth import EmployeeAuth

CODES = {"E01": "1111", "E02": "2222"}
SECRET = "test-secret-not-for-production-0123456789"


def make_auth(**kwargs) -> EmployeeAuth:
    return EmployeeAuth(CODES, SECRET, **kwargs)


def token_for(auth: EmployeeAuth, employee_id: str = "E01") -> str:
    return auth.issue(employee_id)


def authed(app, auth: EmployeeAuth, employee_id: str = "E01") -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {token_for(auth, employee_id)}"})
