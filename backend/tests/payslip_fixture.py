"""A dummy payslip for tests: an A4 page at 200 dpi with made-up numbers, as PNG, JPEG or a 2-page PDF.

Noise in the background, like a scan, so the JPEG is big enough to need shrinking.
"""
import io
from functools import lru_cache

from PIL import Image, ImageDraw

LINES = [
    "STRAUSS - PAYSLIP (DEMO)",
    "Base salary 12,000.00",
    "Commission 1,500.00",
    "Pension employee 6%",
    "Credit points 2.25",
]
# What the fake image model "reads" from it (the real model is never called in tests)
READ = {"base": 12000, "commission": 1500, "bonus": None, "pension_pct": 6, "keren_pct": None,
        "credit_points": 2.25, "current_participation": None}
FOUND = {k: v for k, v in READ.items() if v is not None}


def page(size=(1654, 2339), marker="page 1") -> Image.Image:
    noise = Image.effect_noise(size, 40).convert("RGB")
    img = Image.blend(Image.new("RGB", size, "white"), noise, 0.35)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(LINES + [marker]):
        draw.text((200, 200 + i * 120), line, fill="black")
    return img


def as_bytes(img: Image.Image, fmt: str, **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **kwargs)
    return buf.getvalue()


@lru_cache(maxsize=None)
def png() -> bytes:
    return as_bytes(page(), "PNG")


@lru_cache(maxsize=None)
def jpeg() -> bytes:
    return as_bytes(page(), "JPEG", quality=95)


@lru_cache(maxsize=None)
def pdf() -> bytes:
    """Two pages; the first is portrait, the second landscape - so the first is the one taken."""
    first, second = page(marker="page 1"), page(size=(2339, 1654), marker="page 2")
    return as_bytes(first, "PDF", save_all=True, append_images=[second], resolution=200)
