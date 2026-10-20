"""Payslip: the file (type, size, shrinking, PDF's first page), the extraction (fixed structure, guarded in
code), the note the agent gets, and what reaches LangSmith. Fake models only."""
import io
import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langsmith.utils import tracing_is_enabled
from PIL import Image

from app import payslip, tracing
from app.agent.advisor import load_agent_config
from app.agent.models import ModelStalledError
from tests import payslip_fixture as dummy
from tests.conftest import BACKEND_DIR


@pytest.fixture(scope="module")
def cfg():
    return load_agent_config(BACKEND_DIR)


def size_of(jpeg: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(jpeg)).size


# --- the file ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["png", "jpeg", "pdf"])
def test_the_type_comes_from_the_bytes(kind):
    assert payslip.sniff(getattr(dummy, kind)()) == kind


@pytest.mark.parametrize("raw", [b"GIF89a....", b"hello", b"", b"<svg></svg>"])
def test_other_files_are_refused(cfg, raw):
    assert payslip.sniff(raw) is None
    with pytest.raises(payslip.PayslipError) as e:
        payslip.prepare(raw, cfg["payslip"])
    assert e.value.code == "bad_type"


def test_too_large_is_refused(cfg):
    raw = dummy.png() + b"\0" * (cfg["payslip"]["maxBytes"])
    with pytest.raises(payslip.PayslipError) as e:
        payslip.prepare(raw, cfg["payslip"])
    assert e.value.code == "too_large"


def test_a_broken_image_is_unreadable(cfg):
    with pytest.raises(payslip.PayslipError) as e:
        payslip.prepare(b"\x89PNG\r\n\x1a\n" + b"broken", cfg["payslip"])
    assert e.value.code == "unreadable"


@pytest.mark.parametrize("kind", ["png", "jpeg", "pdf"])
def test_stored_copy_is_a_small_jpeg_with_long_side_1200(cfg, kind):
    p = cfg["payslip"]
    out = payslip.prepare(getattr(dummy, kind)(), p)
    assert payslip.sniff(out.stored) == "jpeg"
    assert max(size_of(out.stored)) == p["storeLongSide"]
    assert len(out.stored) <= p["storeTargetBytes"]
    # the model gets a sharper copy, so small print is still readable
    assert payslip.sniff(out.for_model) == "jpeg"
    assert max(size_of(out.for_model)) == p["extractLongSide"]


def test_pdf_takes_the_first_page(cfg):
    out = payslip.prepare(dummy.pdf(), cfg["payslip"])
    w, h = size_of(out.stored)
    assert h > w  # the first page is portrait; the second (landscape) is ignored


def test_a_small_image_is_not_enlarged(cfg):
    out = payslip.prepare(dummy.as_bytes(dummy.page(size=(600, 800)), "PNG"), cfg["payslip"])
    assert size_of(out.stored) == (600, 800)


# --- the fields -------------------------------------------------------------------------------


def test_fields_in_a_fixed_structure(cfg):
    text = "```json\n" + json.dumps(dummy.READ) + "\n```"
    assert payslip.parse_fields(text, cfg) == dummy.FOUND


def test_numbers_written_as_text_are_read_in_code(cfg):
    assert payslip.parse_fields('{"base": "12,000.00", "pension_pct": "6%"}', cfg) == {"base": 12000, "pension_pct": 6}


def test_unknown_keys_bad_values_and_out_of_range_are_dropped(cfg):
    text = json.dumps({"base": 12000, "name": "ישראל", "id_number": 123456789, "pension_pct": 60,
                       "credit_points": "הרבה", "bonus": True, "commission": -5})
    assert payslip.parse_fields(text, cfg) == {"base": 12000}


@pytest.mark.parametrize("text", ["", "לא מצאתי", "[1, 2]", "{broken"])
def test_not_json_is_nothing(cfg, text):
    assert payslip.parse_fields(text, cfg) == {}


# --- the reader -------------------------------------------------------------------------------


class Reader(GenericFakeChatModel):
    """Answers with fixed text and keeps what it was sent, and whether tracing was on while it ran."""
    seen: list = []
    traced: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        self.traced.append(tracing_is_enabled())
        return super()._generate(messages, stop, run_manager, **kwargs)


class Broken(GenericFakeChatModel):
    def _generate(self, *args, **kwargs):
        raise RuntimeError("503")


def reader_model(answer=None):
    return Reader(messages=iter([AIMessage(content=answer if answer is not None else json.dumps(dummy.READ))]),
                  seen=[], traced=[])


def test_the_model_sees_the_image_once_and_returns_the_fields(cfg):
    model = reader_model()
    reading = payslip.PayslipReader(model, None, cfg).read_image(b"\xff\xd8\xffjpeg")
    assert reading.status == "ok" and reading.fields == dummy.FOUND
    [[msg]] = model.seen
    images = [p for p in msg.content if p.get("type") == "image_url"]
    assert len(images) == 1 and images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert reading.answers  # the call's tokens, for the cost of the question


def test_pasted_text_goes_through_the_same_extraction(cfg):
    model = reader_model()
    reading = payslip.PayslipReader(None, model, cfg).read_text("שכר יסוד 12,000 ...")
    assert reading.status == "ok" and reading.fields == dummy.FOUND
    [[msg]] = model.seen
    assert "שכר יסוד 12,000" in msg.content[1]["text"] and not any(p.get("type") == "image_url" for p in msg.content)


def test_no_model_that_reads_images(cfg):
    reading = payslip.PayslipReader(None, reader_model(), cfg).read_image(b"\xff\xd8\xff")
    assert reading.status == "no_vision" and reading.fields == {}


@pytest.mark.parametrize("model", [Broken(messages=iter([])), reader_model("לא הצלחתי לקרוא"), reader_model("{}")])
def test_a_failed_or_empty_extraction(cfg, model):
    reading = payslip.PayslipReader(model, model, cfg).read_image(b"\xff\xd8\xff")
    assert reading.status == "failed" and reading.fields == {}


def test_a_model_that_goes_silent_is_a_failed_extraction(cfg):
    class Silent(GenericFakeChatModel):
        def _generate(self, *args, **kwargs):
            raise ModelStalledError("silent")

    assert payslip.PayslipReader(Silent(messages=iter([])), None, cfg).read_image(b"\xff\xd8\xff").status == "failed"


def test_long_pasted_text_is_cut(cfg):
    model = reader_model()
    payslip.PayslipReader(None, model, cfg).read_text("א" * (cfg["payslip"]["maxTextChars"] + 500))
    assert "א" * (cfg["payslip"]["maxTextChars"] + 1) not in model.seen[0][0].content[1]["text"]


# --- LangSmith --------------------------------------------------------------------------------


def test_the_image_never_reaches_langsmith(cfg):
    """Tracing on for the whole process, and still off inside the extraction call."""
    tracing.configure({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2-test-not-a-real-key"})
    try:
        model = reader_model()
        payslip.PayslipReader(model, model, cfg).read_image(b"\xff\xd8\xff")
        assert tracing_is_enabled() and model.traced == [False]
    finally:
        tracing.configure({})


def test_the_upload_is_traced_by_name_only():
    assert payslip.trace_upload.__name__ == "trace_upload"
    out = payslip.trace_upload("tid", "image", "ok", ["base", "credit_points"])
    assert out == {"event": "payslip_uploaded", "kind": "image", "status": "ok", "found": ["base", "credit_points"]}


# --- the note to the agent --------------------------------------------------------------------


def test_the_note_lists_found_and_missing_fields(cfg):
    msg = payslip.note(dummy.FOUND, "ok", cfg)
    t = cfg["texts"]["payslip"]
    assert isinstance(msg, HumanMessage) and msg.content.startswith(t["notePrefix"])
    assert "שכר בסיס 12,000" in msg.content and "נקודות זיכוי 2.25" in msg.content
    assert "לא נמצא בתלוש: בונוס" in msg.content
    assert msg.additional_kwargs["kobi_payslip"] == {"status": "ok", "fields": dummy.FOUND, "source": "image"}


def test_fields_of_takes_the_latest_payslip(cfg):
    history = [payslip.note({"base": 9000}, "ok", cfg), HumanMessage(content="עוד שאלה"),
               payslip.note({"base": 12000, "credit_points": 2.25}, "ok", cfg),
               payslip.note({}, "failed", cfg)]  # a later failed upload does not erase what was read
    assert payslip.fields_of(history) == {"base": 12000, "credit_points": 2.25}
    assert payslip.fields_of([HumanMessage(content="x")]) == {}
