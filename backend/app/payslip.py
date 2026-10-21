"""Payslip upload: the file, the extraction, and the note the agent gets. No agent here.

- The file: JPG/PNG/PDF, recognised by its bytes (not by the header it came with), up to payslip.maxBytes.
  A PDF gives its first page. Two JPEG copies: a small one to keep with the conversation (long side
  storeLongSide, about storeTargetBytes) and a sharper one for the model (extractLongSide).
- The extraction: the model sees the image (or the pasted text) once and answers JSON in a fixed structure.
  The values are checked in code (known fields, numbers, config ranges); anything else is dropped.
- The agent never sees the image: it gets a note (a human message from the system) with the values, kept in
  the conversation like any message. calculate fills fields the model did not pass from the latest note
  (app/agent/advisor.py), so the numbers on the payslip reach the calculation as read, not as copied.
- LangSmith: the extraction runs with tracing off (the image and the pasted text never leave), and only
  "payslip_uploaded" is traced, with the names of the fields found.

All texts and settings: config/agent.json ("payslip", "texts.payslip").
"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from langchain_core.messages import BaseMessage, HumanMessage
from langsmith import traceable
from langsmith.run_helpers import tracing_context
from PIL import Image, ImageOps

from app.agent.models import ModelStalledError

NOTE_KEY = "kobi_payslip"  # marks the note in the conversation (additional_kwargs - never sent to the model)
Image.MAX_IMAGE_PIXELS = 60_000_000  # a decompression bomb is "unreadable", not a crash
QUALITIES = (85, 75, 65, 55, 45, 35)


class PayslipError(ValueError):
    """code: too_large | bad_type | unreadable - each has a text in texts.payslip."""

    TEXT_KEYS = {"too_large": "tooLarge", "bad_type": "badType", "unreadable": "unreadable"}

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.text_key = self.TEXT_KEYS[code]


# --- the file ----------------------------------------------------------------------------------


def sniff(raw: bytes) -> Optional[str]:
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"%PDF-"):
        return "pdf"
    return None


@dataclass
class Prepared:
    stored: bytes     # kept with the conversation
    for_model: bytes  # read once by the model, not kept


def _open(raw: bytes, kind: str, long_side: int) -> Image.Image:
    if kind == "pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(raw)
        try:
            page = pdf[0]
            w, h = page.get_size()  # points
            return page.render(scale=long_side / max(w, h)).to_pil()
        finally:
            pdf.close()
    img = Image.open(io.BytesIO(raw))
    img.load()
    return ImageOps.exif_transpose(img)  # a phone photo stays upright


def _shrink(img: Image.Image, long_side: int) -> Image.Image:
    img = img.convert("RGB")
    scale = long_side / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img


def _jpeg(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _small_jpeg(img: Image.Image, target: int) -> bytes:
    """The best quality that fits the target; the lowest one if none does."""
    out = b""
    for q in QUALITIES:
        out = _jpeg(img, q)
        if len(out) <= target:
            break
    return out


def prepare(raw: bytes, settings: dict) -> Prepared:
    """settings: config/agent.json "payslip"."""
    if len(raw) > settings["maxBytes"]:
        raise PayslipError("too_large")
    kind = sniff(raw)
    if kind is None:
        raise PayslipError("bad_type")
    try:
        img = _open(raw, kind, settings["extractLongSide"])
        for_model = _shrink(img, settings["extractLongSide"])
        stored = _shrink(for_model, settings["storeLongSide"])
    except Exception as e:  # noqa: BLE001 - a broken or hostile file: the employee gets a calm message
        raise PayslipError("unreadable") from e
    return Prepared(stored=_small_jpeg(stored, settings["storeTargetBytes"]), for_model=_jpeg(for_model, 85))


# --- the fields --------------------------------------------------------------------------------


def _number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("%", "").replace("₪", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_fields(text: str, cfg: dict) -> dict:
    """The model's answer -> {field: number}. Only payslip.fields, only numbers inside the config ranges."""
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        raw = json.loads(match.group(0)) if match else None
    except ValueError:
        raw = None
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name in cfg["payslip"]["fields"]:
        x = _number(raw.get(name))
        lo, hi = cfg["ranges"][name]
        if x is not None and lo <= x <= hi:
            out[name] = int(x) if x == int(x) else x
    return out


# --- the reader --------------------------------------------------------------------------------


@dataclass
class Reading:
    status: str  # ok | no_vision | failed
    fields: dict = field(default_factory=dict)
    answers: list = field(default_factory=list)  # the model's messages, for the cost of the question


class PayslipReader:
    """image_model: a chain of the models that read images, or None (none configured).
    text_model: any chain (pasted text)."""

    def __init__(self, image_model, text_model, cfg: dict):
        self.image_model = image_model
        self.text_model = text_model
        self.cfg = cfg
        self.prompt = cfg["texts"]["payslip"]["extractPrompt"]

    def _read(self, model, content: list) -> Reading:
        if model is None:
            return Reading("no_vision")
        try:
            # tracing off: the image (or the pasted payslip) never reaches LangSmith
            with tracing_context(enabled=False):
                answer = model.invoke([HumanMessage(content=content)])
        except (Exception, ModelStalledError):  # every model failed - the employee answers the questions
            return Reading("failed")
        from app.api.common import text_of

        fields = parse_fields(text_of(answer.content), self.cfg)
        return Reading("ok" if fields else "failed", fields, [answer])

    def read_image(self, jpeg: bytes) -> Reading:
        url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        return self._read(self.image_model, [{"type": "text", "text": self.prompt},
                                             {"type": "image_url", "image_url": {"url": url}}])

    def read_text(self, text: str) -> Reading:
        text = text[: self.cfg["payslip"]["maxTextChars"]]
        return self._read(self.text_model, [{"type": "text", "text": self.prompt},
                                            {"type": "text", "text": text}])


@traceable(name="payslip_uploaded", run_type="chain")
def trace_upload(thread_id: str, kind: str, status: str, found: list[str]) -> dict:
    """The only LangSmith trace of an upload: which fields were found - no image, no text, no values."""
    return {"event": "payslip_uploaded", "kind": kind, "status": status, "found": found}


# --- the note to the agent ---------------------------------------------------------------------


def _shown(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def note(fields: dict, status: str, cfg: dict, source: str = "image", profile_updated: bool = False) -> HumanMessage:
    """What the agent gets after an upload, built in code: the values as read, and what was not found.
    source: image | text (what the screen shows in its place). profile_updated: the values went to the
    employee's profile as well (Kobi says "עדכנתי בפרופיל")."""
    t = cfg["texts"]["payslip"]
    labels = t["labels"]
    parts = [t["notePrefix"]]
    if fields:
        parts.append(t["noteFound"].format(found=", ".join(f"{labels[k]} {_shown(v)}" for k, v in fields.items())))
    missing = [labels[k] for k in cfg["payslip"]["fields"] if k not in fields]
    if missing and status == "ok":
        parts.append(t["noteMissing"].format(missing=", ".join(missing)))
    if profile_updated:
        parts.append(cfg["texts"]["profile"]["noteUpdated"])
    return HumanMessage(content=" ".join(parts) + t["noteEnd"],
                        additional_kwargs={NOTE_KEY: {"status": status, "fields": dict(fields), "source": source}})


def is_note(msg: BaseMessage) -> bool:
    return NOTE_KEY in (getattr(msg, "additional_kwargs", None) or {})


def fields_of(history: Iterable) -> dict:
    """The fields of the latest payslip that had any (a later failed upload does not erase them)."""
    for msg in reversed(list(history)):
        if is_note(msg) and msg.additional_kwargs[NOTE_KEY].get("fields"):
            return dict(msg.additional_kwargs[NOTE_KEY]["fields"])
    return {}


# --- storage -----------------------------------------------------------------------------------


class InMemoryPayslips:
    """One payslip per conversation (a new upload replaces it). app/db.py has the Postgres version
    (tests/test_payslip_repository.py runs on both)."""

    def __init__(self):
        self._rows: dict[str, dict] = {}

    def save(self, thread_id: str, image: Optional[bytes], source: str) -> None:
        """source: image | text (pasted text keeps no image, and the text itself is not kept)."""
        self._rows[thread_id] = {"image": image, "source": source, "fields": None,
                                 "created_at": datetime.now(timezone.utc).isoformat()}

    def set_fields(self, thread_id: str, fields: dict) -> None:
        if thread_id in self._rows:
            self._rows[thread_id]["fields"] = dict(fields)

    def get(self, thread_id: str) -> Optional[dict]:
        row = self._rows.get(thread_id)
        return dict(row) if row else None

    def delete(self, thread_id: str) -> None:
        self._rows.pop(thread_id, None)
