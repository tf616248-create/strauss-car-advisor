"""The server is split: employee routes in app/api/employee.py, rep routes in app/api/rep.py.

Every rep route is behind the passcode as a whole (on the router), not route by route.
"""
from fastapi.routing import APIRoute

from app.agent.rep_queue import InMemoryRepQueue
from app.api import employee, rep
from app.api.events import InMemoryNotifier
from tests.test_agent_graph import ScriptedModel
from tests.test_api import PASS, cfg, make  # noqa: F401 (cfg is a fixture)


def paths(router):
    return {r.path for r in router.routes if isinstance(r, APIRoute)}


def build_routers(data, cfg):
    from app.agent.graph import build_agent

    queue = InMemoryRepQueue()
    agent = build_agent(ScriptedModel(messages=iter([])), data, queue, cfg)
    return (employee.router(agent=agent, rep_queue=queue, notifier=InMemoryNotifier(), cfg=cfg),
            rep.router(agent=agent, rep_queue=queue, notifier=InMemoryNotifier(), rep_passcode=PASS))


def test_employee_routes_and_rep_routes_live_in_separate_modules(data, cfg):
    emp, rp = build_routers(data, cfg)
    assert paths(emp) == {"/chat", "/chat/{thread_id}/rep-answered", "/chat/{thread_id}",
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


def test_health_stays_on_the_app(data, cfg):
    client, _, _ = make(data, cfg, script=[])
    assert client.get("/health").status_code == 200
