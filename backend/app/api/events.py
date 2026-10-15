"""'Something changed in this conversation' - from the server to the employee's browser over SSE.

The database is the source of truth; SSE only rings. An event carries no data:
the browser reads the current state from the server (GET /chat/{id}).

The list of open connections lives in this process's memory, so the server runs
one worker (render.yaml). More processes need a shared channel (e.g. Postgres
LISTEN/NOTIFY) behind the same publish/subscribe - see CLAUDE.md.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Optional

CHANGED = "changed"


class InMemoryNotifier:
    def __init__(self):
        self._subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._lock = threading.Lock()

    def publish(self, conversation_id: str) -> None:
        """Safe from any thread: the rep's answer is handled in a worker thread."""
        with self._lock:
            subs = list(self._subs.get(conversation_id, ()))
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, CHANGED)
            except RuntimeError:  # that browser's loop is gone
                pass

    @asynccontextmanager
    async def subscribe(self, conversation_id: str) -> AsyncIterator[asyncio.Queue]:
        entry = (asyncio.get_running_loop(), asyncio.Queue())
        with self._lock:
            self._subs.setdefault(conversation_id, set()).add(entry)
        try:
            yield entry[1]
        finally:
            with self._lock:
                subs = self._subs.get(conversation_id)
                if subs is not None:
                    subs.discard(entry)
                    if not subs:
                        del self._subs[conversation_id]

    def subscriber_count(self, conversation_id: str) -> int:
        with self._lock:
            return len(self._subs.get(conversation_id, ()))


async def conversation_events(notifier, conversation_id: str, heartbeat: float,
                              is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None):
    """The SSE body: "changed" with no data, and a comment line every `heartbeat` seconds
    so proxies and Render keep the connection open."""
    async with notifier.subscribe(conversation_id) as queue:
        yield "retry: 3000\n: connected\n\n"
        while True:
            try:
                await asyncio.wait_for(queue.get(), heartbeat)
                chunk = f"event: {CHANGED}\ndata: {{}}\n\n"
            except asyncio.TimeoutError:
                chunk = ": ping\n\n"
            if is_disconnected is not None and await is_disconnected():
                return
            yield chunk
