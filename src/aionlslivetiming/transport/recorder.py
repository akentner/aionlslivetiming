"""JSONL recorder (Phase 3 file-format contract).

Append-only file with the Phase 3 schema::

    {"ts_recv_ms": <int>, "event_pid": <int>, "raw": <obj>, "parsed": <obj>}

This is a strict superset of Phase 1's D-07 shape ({"ts_recv_ms", "raw"}),
so a D-07 JSONL is always replayable. The writer runs on a dedicated
asyncio.Task fed by an asyncio.Queue, so `append()` is non-blocking and
concurrent calls cannot interleave partial lines (Pitfall #7).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json as _stdlib_json
import pathlib
import time
from typing import TYPE_CHECKING, Any

from aionlslivetiming.logging import get_logger

if TYPE_CHECKING:
    from aionlslivetiming.events import Message

_log = get_logger("aionlslivetiming.transport.recorder")

_SENTINEL_CLOSE: object = object()


def _dumps(obj: Any) -> str:
    """Serialize; orjson if available, stdlib json fallback (D-10)."""
    try:
        import orjson  # type: ignore[import-not-found]
        result: str = orjson.dumps(obj).decode("utf-8")
        return result
    except ImportError:
        return _stdlib_json.dumps(obj, separators=(",", ":"))


def _serialise_parsed(msg: Any) -> Any:
    """Serialise a Message to a JSON-friendly shape.

    Events layer is stdlib dataclasses — use `dataclasses.asdict` to get
    a plain dict. pydantic state objects use `model_dump(mode="json")`.
    UnknownMessage carries the raw payload — preserve it verbatim.
    """
    if dataclasses.is_dataclass(msg) and not isinstance(msg, type):
        return dataclasses.asdict(msg)
    model_dump = getattr(msg, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return dict(msg.raw)


class JsonlRecorder:
    """Async append-only JSONL recorder with an isolated writer task.

    Usage::

        rec = JsonlRecorder(path)
        await rec.append(msg)            # non-blocking
        await rec.append(msg)
        await rec.close()                # flush + join writer task

    Or as an async context manager::

        async with JsonlRecorder(path) as rec:
            await rec.append(msg)

    The file is opened lazily on the first `append()` call. The writer task
    runs forever (awaiting the queue) until `close()` is called or the
    sentinel is enqueued. Concurrent `append()` calls are safe — the queue
    serialises them and the writer writes one complete line at a time.
    """

    def __init__(self, path: str | pathlib.Path) -> None:
        self._path = pathlib.Path(path)
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def path(self) -> pathlib.Path:
        return self._path

    async def __aenter__(self) -> JsonlRecorder:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def append(self, msg: Message) -> None:
        """Enqueue a message for writing. Non-blocking.

        Returns immediately after queueing. The actual file write happens
        on the writer task. Raises RuntimeError if already closed.
        """
        if self._closed:
            raise RuntimeError("JsonlRecorder is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._writer_loop())
        await self._queue.put(msg)

    async def close(self) -> None:
        """Flush pending writes and stop the writer task. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._task is not None:
            await self._queue.put(_SENTINEL_CLOSE)
            await self._task
            self._task = None

    async def _writer_loop(self) -> None:
        """Drain the queue, writing one line per message. Exits on sentinel."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Open in append mode so multiple rec sessions on the same path concatenate.
        with self._path.open("a", encoding="utf-8") as fh:
            while True:
                item = await self._queue.get()
                if item is _SENTINEL_CLOSE:
                    return
                line = _dumps({
                    "ts_recv_ms": int(time.time() * 1000),
                    "event_pid": int(item.event_pid),
                    "raw": dict(item.raw),
                    "parsed": _serialise_parsed(item),
                })
                fh.write(line + "\n")
                fh.flush()


__all__ = ["JsonlRecorder"]
