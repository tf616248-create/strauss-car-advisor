"""The employee's first name in Kobi's answers, put in by the server - never seen by the model.

The prompt has only the placeholder (agent.json address.placeholder, "{name}"), so the name never reaches
the model's input or LangSmith. The server replaces it as the answer streams to the employee (NameFiller)
and when a conversation is read again (fill). Without a name the placeholder goes, with the space before it.
"""
from __future__ import annotations

import re
from typing import Optional

PLACEHOLDER = "{name}"
_WITH_SPACE = re.compile(r"\s*" + re.escape(PLACEHOLDER))


def first_name(full: Optional[str]) -> Optional[str]:
    parts = (full or "").split()
    return parts[0] if parts else None


def fill(text: str, name: Optional[str]) -> str:
    if name:
        return text.replace(PLACEHOLDER, name)
    return _WITH_SPACE.sub("", text)


class NameFiller:
    """fill() for a stream: holds back what may still turn into the placeholder ("{na" waits for "me}"),
    and the whitespace before it (so that without a name no stray space is left)."""

    def __init__(self, name: Optional[str]):
        self.name = name
        self.held = ""

    def feed(self, text: str) -> str:
        self.held = fill(self.held + text, self.name)
        keep = self._open_tail(self.held)
        out, self.held = self.held[:len(self.held) - keep], self.held[len(self.held) - keep:]
        return out

    def flush(self) -> str:
        out, self.held = self.held, ""
        return out

    @staticmethod
    def _open_tail(text: str) -> int:
        """How many characters at the end may still be part of a placeholder (with whitespace before it)."""
        for n in range(min(len(PLACEHOLDER) - 1, len(text)), 0, -1):
            if PLACEHOLDER.startswith(text[-n:]):
                start = len(text) - n
                while start > 0 and text[start - 1].isspace():
                    start -= 1
                return len(text) - start
        stripped = text.rstrip()
        return len(text) - len(stripped)  # trailing whitespace waits for what comes next
