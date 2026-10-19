"""Employee login (demo codes -> JWT) and conversation history that belongs to the employee.

Each employee sees and writes only their own conversations; anyone else's is 404 (not 403),
so a guessed id says nothing about whether it exists.
"""
import jwt
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.advisor import load_agent_config
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.auth import EmployeeAuth, LoginLimiter
from app.threads import InMemoryThreads
from tests.auth_helpers import CODES, SECRET, authed, make_auth
from tests.conftest import BACKEND_DIR
from tests.test_agent_advisor import employee_args
from tests.test_agent_graph import ScriptedModel, call
from tests.test_api import events


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


# --- the login itself ------------------------------------------------------------


def test_a_right_code_gives_the_employee_id():
    auth = make_auth()
    assert auth.login("1111") == "E01"
    assert auth.login("2222") == "E02"
    assert auth.login("3333") is None
    assert auth.login("") is None


def test_token_round_trip():
    auth = make_auth()
    assert auth.verify(auth.issue("E02")) == "E02"


def test_token_expires_after_the_configured_hours():
    clock = [1_000_000.0]
    auth = make_auth(hours=8, now=lambda: clock[0])
    token = auth.issue("E01")
    clock[0] += 8 * 3600 - 5
    assert auth.verify(token) == "E01"
    clock[0] += 10
    assert auth.verify(token) is None


def test_a_forged_or_broken_token_is_refused():
    auth = make_auth()
    other = EmployeeAuth(CODES, "another-secret-another-secret-0123456789")
    assert auth.verify(other.issue("E01")) is None  # signed with another secret
    assert auth.verify("not-a-token") is None
    assert auth.verify("") is None
    unsigned = jwt.encode({"sub": "E01"}, key=None, algorithm="none")
    assert auth.verify(unsigned) is None  # alg "none" is never accepted


def test_a_token_for_a_removed_code_is_refused():
    token = make_auth().issue("E09")  # E09 is not in the list (e.g. removed from .env)
    assert make_auth().verify(token) is None


def test_codes_and_secret_come_from_the_environment():
    auth = EmployeeAuth.from_env({"EMPLOYEE_CODES": " E01:1111 , E02:2222 ", "JWT_SECRET": SECRET}, hours=8)
    assert auth.login("2222") == "E02"
    assert EmployeeAuth.from_env({"JWT_SECRET": SECRET}, hours=8) is None  # no codes: login is closed


def test_without_a_secret_a_random_one_is_used():
    """Local only: tokens then die with the server. Render sets JWT_SECRET (render.yaml)."""
    a = EmployeeAuth.from_env({"EMPLOYEE_CODES": "E01:1111"}, hours=8)
    b = EmployeeAuth.from_env({"EMPLOYEE_CODES": "E01:1111"}, hours=8)
    assert a.verify(a.issue("E01")) == "E01"
    assert b.verify(a.issue("E01")) is None


def test_a_bad_codes_line_stops_the_server():
    with pytest.raises(ValueError):
        EmployeeAuth.from_env({"EMPLOYEE_CODES": "E01:1111,E02", "JWT_SECRET": SECRET}, hours=8)
    with pytest.raises(ValueError):  # two employees with one code: the login can't tell them apart
        EmployeeAuth.from_env({"EMPLOYEE_CODES": "E01:1111,E02:1111", "JWT_SECRET": SECRET}, hours=8)


def test_limiter_blocks_after_too_many_failures_then_lets_go():
    clock = [0.0]
    lim = LoginLimiter(max_failures=3, window_seconds=60, now=lambda: clock[0])
    for _ in range(3):
        assert lim.allowed("ip")
        lim.failed("ip")
    assert not lim.allowed("ip")
    assert lim.allowed("other-ip")
    clock[0] += 61
    assert lim.allowed("ip")


def test_auth_settings_in_the_config(cfg):
    a = cfg["auth"]
    assert a["tokenHours"] == 8
    assert a["maxFailedLogins"] > 0 and a["failedLoginWindowSeconds"] > 0


# --- the API ---------------------------------------------------------------------


def build(data, cfg, script=(), auth="default", threads=None):
    auth = make_auth() if auth == "default" else auth
    threads = threads if threads is not None else InMemoryThreads()
    app = create_app(data=data, model=ScriptedModel(messages=iter(list(script))), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode=None, employee_auth=auth, threads=threads)
    return app, auth, threads


def new_thread(client, message="שלום"):
    evs = events(client.post("/chat", json={"message": message}))
    return evs[0][1]["thread_id"]


def test_login_endpoint(data, cfg):
    app, auth, _ = build(data, cfg)
    client = TestClient(app)
    r = client.post("/login", json={"code": "2222"})
    assert r.status_code == 200
    assert auth.verify(r.json()["token"]) == "E02"
    assert client.post("/login", json={"code": "9999"}).status_code == 401


def test_too_many_wrong_codes_are_slowed_down(data, cfg):
    app, _, _ = build(data, cfg)
    client = TestClient(app)
    for _ in range(cfg["auth"]["maxFailedLogins"]):
        assert client.post("/login", json={"code": "0000"}).status_code == 401
    assert client.post("/login", json={"code": "1111"}).status_code == 429  # even the right code, for now


def test_no_codes_configured_means_the_employee_screen_is_closed(data, cfg):
    app, _, _ = build(data, cfg, auth=None)
    client = TestClient(app)
    assert client.post("/login", json={"code": "1111"}).status_code == 503
    assert client.post("/chat", json={"message": "שלום"}).status_code == 503


def test_every_employee_route_needs_a_token(data, cfg):
    app, _, _ = build(data, cfg)
    client = TestClient(app)
    tid = "11111111-2222-3333-4444-555555555555"
    assert client.post("/chat", json={"message": "שלום"}).status_code == 401
    assert client.get(f"/chat/{tid}").status_code == 401
    assert client.post(f"/chat/{tid}/rep-answered").status_code == 401
    assert client.get(f"/conversations/{tid}/events").status_code == 401
    assert client.get("/threads").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/threads", headers=bad).status_code == 401
    assert client.get("/health").status_code == 200  # health stays open (UptimeRobot)


def test_a_new_conversation_belongs_to_its_employee(data, cfg):
    app, auth, threads = build(data, cfg, script=[AIMessage(content="היי")])
    tid = new_thread(authed(app, auth, "E01"))
    assert threads.owner(tid) == "E01"


def test_another_employees_conversation_is_404_everywhere(data, cfg):
    app, auth, _ = build(data, cfg, script=[AIMessage(content="היי")])
    tid = new_thread(authed(app, auth, "E01"))
    other = authed(app, auth, "E02")
    assert other.get(f"/chat/{tid}").status_code == 404
    assert other.post("/chat", json={"message": "שלום", "thread_id": tid}).status_code == 404
    assert other.post(f"/chat/{tid}/rep-answered").status_code == 404
    assert other.get(f"/conversations/{tid}/events").status_code == 404
    assert authed(app, auth, "E01").get(f"/chat/{tid}").status_code == 200


def test_a_conversation_from_before_logins_belongs_to_nobody(data, cfg):
    app, auth, _ = build(data, cfg)
    tid = "11111111-2222-3333-4444-555555555555"
    assert authed(app, auth).post("/chat", json={"message": "שלום", "thread_id": tid}).status_code == 404


def test_history_lists_only_my_conversations_newest_first_with_a_title(data, cfg):
    script = [AIMessage(content="היי"),
              call("calculate", employee_args(data, "E-001")), AIMessage(content="סיום"),
              AIMessage(content="היי")]
    app, auth, _ = build(data, cfg, script=script)
    me, other = authed(app, auth, "E01"), authed(app, auth, "E02")
    first = new_thread(me, "שאלה ראשונה שלי על הרכב")
    second = new_thread(me, "מה יקרה לנטו?")
    new_thread(other, "של מישהו אחר")

    listed = me.get("/threads").json()["threads"]
    assert [t["thread_id"] for t in listed] == [second, first]
    assert listed[1]["title"] == "שאלה ראשונה שלי על הרכב"  # no card: the first question
    card = me.get(f"/chat/{second}").json()["cards"][0]["card"]
    assert listed[0]["title"] == card["alternative"]["label"]  # a card: the alternative asked about
    assert listed[0]["updated_at"]


def test_events_take_the_token_in_the_url(data, cfg):
    """EventSource can't send headers, so the events stream reads ?token= (a short-lived token)."""
    app, auth, threads = build(data, cfg)
    tid = "11111111-2222-3333-4444-555555555555"
    threads.add("E01", tid)
    client = TestClient(app)
    with client.stream("GET", f"/conversations/{tid}/events?token=bad") as r:
        assert r.status_code == 401
    with client.stream("GET", f"/conversations/{tid}/events?token={auth.issue('E02')}") as r:
        assert r.status_code == 404  # a valid token, but not their conversation
    # a valid token for the owner opens the stream: test_events.py


def test_long_titles_are_cut(data, cfg):
    app, auth, _ = build(data, cfg, script=[AIMessage(content="היי")])
    me = authed(app, auth)
    new_thread(me, "א" * 200)
    [t] = me.get("/threads").json()["threads"]
    assert len(t["title"]) <= 61 and t["title"].endswith("…")


def test_the_rep_answered_note_is_not_a_title(data, cfg):
    from app.api.common import title_of
    from langchain_core.messages import HumanMessage

    note = cfg["texts"]["repAnswered"]
    assert title_of([HumanMessage(content=note), HumanMessage(content="שאלה")], note) == "שאלה"
    assert title_of([], note) == "שיחה"


def test_requirements_pin_pyjwt():
    assert "PyJWT" in (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")


def test_render_declares_the_login_secrets():
    text = (BACKEND_DIR.parent / "render.yaml").read_text(encoding="utf-8")
    assert "EMPLOYEE_CODES" in text and "JWT_SECRET" in text


def test_env_example_lists_the_login_settings():
    text = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    assert "EMPLOYEE_CODES=" in text and "JWT_SECRET=" in text
