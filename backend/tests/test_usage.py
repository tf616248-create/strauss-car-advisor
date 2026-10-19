"""Cost of each question: tokens per model call, summed per question, priced from config/agent.json,
printed to the server log and appended to a local CSV (backend/logs/usage.csv, not in git)."""
import csv
import logging

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.models import WithTimeout
from app.agent.rep_queue import InMemoryRepQueue
from app.api.events import InMemoryNotifier
from app.api.main import create_app
from app.usage import append_row, turn_usage
from tests.test_agent_graph import ScriptedModel, call
from tests.test_api import cfg  # noqa: F401 (fixture)

PRICES = {"gemini": {"inputPerMillionUsd": 0.75, "outputPerMillionUsd": 3.75}}


def ai(inp, out, label="gemini", **kw):
    return AIMessage(content=kw.pop("content", ""), usage_metadata={"input_tokens": inp, "output_tokens": out,
                                                                     "total_tokens": inp + out},
                     response_metadata={"kobi_model": label}, **kw)


def test_one_question_sums_every_model_call():
    msgs = [ai(1000, 100, tool_calls=[{"name": "calculate", "args": {}, "id": "1"}]), ai(3000, 300, content="סיום")]
    u = turn_usage(msgs, PRICES)
    assert (u["calls"], u["input_tokens"], u["output_tokens"]) == (2, 4000, 400)
    assert u["models"] == "gemini"
    assert abs(u["cost_usd"] - (4000 * 0.75 + 400 * 3.75) / 1_000_000) < 1e-12


def test_numbered_gemini_keys_use_the_gemini_price():
    u = turn_usage([ai(1_000_000, 0, label="gemini_2")], PRICES)
    assert u["models"] == "gemini_2"
    assert u["cost_usd"] == 0.75


def test_a_model_without_a_price_gives_no_cost_not_a_guess():
    u = turn_usage([ai(10, 10), ai(10, 10, label="groq")], PRICES)
    assert u["models"] == "gemini+groq"
    assert u["cost_usd"] is None


def test_messages_without_usage_count_as_zero():
    u = turn_usage([AIMessage(content="x")], PRICES)
    assert (u["calls"], u["input_tokens"], u["output_tokens"]) == (1, 0, 0)


def test_csv_gets_a_header_once_and_one_row_per_question(tmp_path):
    path = tmp_path / "logs" / "usage.csv"
    append_row(path, {"time": "t1", "question": "א", "calls": 1, "input_tokens": 5, "output_tokens": 1,
                      "models": "gemini", "cost_usd": 0.001, "thread_id": "x"})
    append_row(path, {"time": "t2", "question": "ב", "calls": 2, "input_tokens": 6, "output_tokens": 2,
                      "models": "gemini", "cost_usd": None, "thread_id": "x"})
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))  # utf-8-sig: Excel opens Hebrew correctly
    assert [r["question"] for r in rows] == ["א", "ב"]
    assert rows[1]["cost_usd"] == ""


def test_the_timeout_wrapper_stamps_which_model_answered():
    wrapped = WithTimeout(ScriptedModel(messages=iter([AIMessage(content="שלום עולם")])), 5, "gemini_3")
    msg = wrapped.invoke("שאלה")
    assert msg.response_metadata["kobi_model"] == "gemini_3"


def test_config_has_a_gemini_price():
    from app.agent.advisor import load_agent_config
    from tests.conftest import BACKEND_DIR

    usage = load_agent_config(BACKEND_DIR)["usage"]
    assert usage["file"] == "logs/usage.csv"
    assert usage["prices"]["gemini"]["inputPerMillionUsd"] > 0
    assert usage["prices"]["gemini"]["outputPerMillionUsd"] > 0


class Metered(ScriptedModel):
    """Every scripted answer reports 100 tokens in, 10 out."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        first = True
        for chunk in super()._stream(messages, stop, run_manager, **kwargs):
            if first:
                chunk.message.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
                first = False
            yield chunk


def test_each_question_is_logged_and_written_to_the_csv(data, cfg, tmp_path, caplog):  # noqa: F811
    from app.agent.models import with_fallbacks
    from tests.test_agent_advisor import employee_args

    model = with_fallbacks([Metered(messages=iter([call("calculate", employee_args(data, "E-001")),
                                                   AIMessage(content="סיום")]))], 5, ["gemini"])
    path = tmp_path / "usage.csv"
    app = create_app(data=data, model=model, rep_queue=InMemoryRepQueue(), notifier=InMemoryNotifier(),
                     cfg=cfg, rep_passcode=None, usage_file=path)
    with caplog.at_level(logging.INFO, logger="app.timing"):
        TestClient(app).post("/chat", json={"message": "מה יקרה לנטו שלי?"})
    [row] = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert (row["calls"], row["input_tokens"], row["output_tokens"], row["models"]) == ("2", "200", "20", "gemini")
    assert row["question"] == "מה יקרה לנטו שלי?"
    assert float(row["cost_usd"]) > 0
    assert any("💲 question:" in r.getMessage() for r in caplog.records)


def test_without_a_usage_file_nothing_is_written(data, cfg, tmp_path):  # noqa: F811
    app = create_app(data=data, model=ScriptedModel(messages=iter([AIMessage(content="היי")])),
                     rep_queue=InMemoryRepQueue(), notifier=InMemoryNotifier(), cfg=cfg, rep_passcode=None)
    TestClient(app).post("/chat", json={"message": "היי"})
    assert not list(tmp_path.iterdir())
