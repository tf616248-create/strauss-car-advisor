"""Employee login for the demo: a code from a short list -> a signed token (JWT).

EMPLOYEE_CODES in .env: "E01:1111,E02:2222,..." (employee id : code). JWT_SECRET signs the tokens;
without it a random one is used, so tokens die with the server (fine locally; Render sets it).
The codes stay as they are in .env: a hash of a 4-digit code is cracked in a moment, so it would
add nothing. For a pilot this layer is replaced by Strauss SSO; the rest of the code only sees
an employee id.

The browser keeps the token in sessionStorage (gone when the tab closes - a shared computer)
and sends it as "Authorization: Bearer ...", not as a cookie: the screen (Netlify) and the
server (Render) are on different domains, and cross-site cookies are blocked by some browsers.
"""
from __future__ import annotations

import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Callable, Mapping, Optional

import jwt

log = logging.getLogger(__name__)
ALGORITHM = "HS256"


class EmployeeAuth:
    def __init__(self, codes: Mapping[str, str], secret: str, hours: float = 8,
                 now: Callable[[], float] = time.time):
        self._codes = dict(codes)  # employee id -> code
        self._secret = secret
        self._seconds = int(hours * 3600)
        self._now = now

    @classmethod
    def from_env(cls, env: Mapping[str, str], hours: float) -> Optional["EmployeeAuth"]:
        """None when EMPLOYEE_CODES is empty: the employee screen is then closed."""
        line = (env.get("EMPLOYEE_CODES") or "").strip()
        if not line:
            return None
        codes = {}
        for item in line.split(","):
            employee, sep, code = item.strip().partition(":")
            if not sep or not employee.strip() or not code.strip():
                raise ValueError(f"EMPLOYEE_CODES: expected id:code, got {item.strip()!r}")
            codes[employee.strip()] = code.strip()
        if len(set(codes.values())) != len(codes):
            raise ValueError("EMPLOYEE_CODES: two employees share a code")
        secret = env.get("JWT_SECRET")
        if not secret:
            log.warning("JWT_SECRET is not set: a random one is used, logins end when the server restarts")
            secret = secrets.token_urlsafe(48)
        return cls(codes, secret, hours)

    def login(self, code: str) -> Optional[str]:
        """The employee id for this code, or None. Compares against every code in constant time."""
        found = None
        for employee, expected in self._codes.items():
            if secrets.compare_digest(str(code).encode(), expected.encode()):
                found = employee
        return found

    def issue(self, employee_id: str) -> str:
        now = int(self._now())
        return jwt.encode({"sub": employee_id, "iat": now, "exp": now + self._seconds},
                          self._secret, algorithm=ALGORITHM)

    def verify(self, token: str) -> Optional[str]:
        """The employee id, or None for a bad, expired, or unknown employee's token."""
        if not token:
            return None
        try:
            claims = jwt.decode(token, self._secret, algorithms=[ALGORITHM],
                                options={"require": ["sub", "exp"], "verify_exp": False, "verify_iat": False})
        except jwt.PyJWTError:
            return None
        if claims["exp"] <= self._now():  # our own clock, so tests can move it
            return None
        employee = claims["sub"]
        return employee if employee in self._codes else None


class LoginLimiter:
    """Too many wrong codes from one address -> wait. 4-digit codes are easy to guess otherwise.
    In memory (one server process, see render.yaml). Keyed by the client address."""

    def __init__(self, max_failures: int, window_seconds: float, now: Callable[[], float] = time.monotonic):
        self._max = max_failures
        self._window = window_seconds
        self._now = now
        self._failures: dict[str, deque] = defaultdict(deque)

    def _recent(self, key: str) -> deque:
        q = self._failures[key]
        while q and q[0] <= self._now() - self._window:
            q.popleft()
        return q

    def allowed(self, key: str) -> bool:
        return len(self._recent(key)) < self._max

    def failed(self, key: str) -> None:
        self._recent(key).append(self._now())
