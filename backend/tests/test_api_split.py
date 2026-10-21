"""The server is split: employee routes in app/api/employee.py, rep routes in app/api/rep.py.

Every rep route is behind the passcode as a whole (on the router), not route by route.
"""
from fastapi.routing import APIRoute

from app.agent.rep_queue import InMemoryRepQueue
from app.api import employee, rep
from app.api.events import InMemoryNotifier
from app.employees import InMemoryEmployees
from app.payslip import InMemoryPayslips, PayslipReader
from app.threads import InMemoryThreads
from tests.auth_helpers import make_auth
from tests.test_agent_graph import ScriptedModel
from tests.test_api import PASS, cfg, make  # noqa: F401 (cfg is a fixture)


def paths(router):
    return {r.path for r in router.routes if isinstance(r, APIRoute)}


def build_routers(data, cfg):
    from app.agent.graph import build_agent

    queue = InMemoryRepQueue()
    agent = build_agent(ScriptedModel(messages=iter([])), data, queue, cfg)
    return (employee.router(agent=agent, rep_queue=queue, notifier=InMemoryNotifier(), cfg=cfg,
                            threads=InMemoryThreads(), payslips=InMemoryPayslips(),
                            payslip_reader=PayslipReader(None, None, cfg), auth=make_auth(),
                            employees=InMemoryEmployees({})),
            rep.router(agent=agent, rep_queue=queue, notifier=InMemoryNotifier(), rep_passcode=PASS))


def test_employee_routes_and_rep_routes_live_in_separate_modules(data, cfg):
    emp, rp = build_routers(data, cfg)
    assert paths(emp) == {"/login", "/me", "/threads", "/chat", "/chat/{thread_id}/rep-answered", "/chat/{thread_id}",
                          "/chat/{thread_id}/payslip", "/chat/{thread_id}/payslip-text",
                          "/conversations/{thread_id}/events"}
    assert paths(rp) == {"/rep/requests", "/rep/requests/{request_id}/answer"}


def test_every_rep_route_needs_the_passcode(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    _, rp = build_routers(data, cfg)
    rep_routes = [r for r in rp.routes if isinstance(r, APIRoute)]
    assert rep_routes
    for r in rep_routes:
        method = next(iter(r.methods))
        url = r.path.replace("{request_id}", "1")
        assert client.request(method, url, json={"values": {"x": 1}}).status_code == 401, r.path


def test_every_employee_route_but_login_needs_a_token(data, cfg):
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    app = create_app(data=data, model=ScriptedModel(messages=iter([])), rep_queue=InMemoryRepQueue(),
                     notifier=InMemoryNotifier(), cfg=cfg, rep_passcode=PASS, employee_auth=make_auth())
    client = TestClient(app)
    emp, _ = build_routers(data, cfg)
    routes = [r for r in emp.routes if isinstance(r, APIRoute) and r.path != "/login"]
    assert routes
    for r in routes:
        method = next(iter(r.methods))
        url = r.path.replace("{thread_id}", "11111111-2222-3333-4444-555555555555")
        assert client.request(method, url, json={"message": "x"}).status_code == 401, r.path


def test_health_stays_on_the_app(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.get("/health").status_code == 200
