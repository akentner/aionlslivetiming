"""Replay transport — reads JSONL line-by-line, yields parsed Messages.

Replay path (ARCHITECTURE.md lines 222-234):
1. Open JSONL, iterate lines.
2. For each line, dispatch `raw` through `parser.parse()` (D-10 invariant).
3. Apply speed_factor timing between successive `ts_recv_ms` values.
4. Optionally yield time-sync messages (D-04/D-16).

Backward compatibility with Phase 1's D-07 line shape `{ts_recv_ms, raw}`:
- Missing `event_pid` falls back to `raw.get("eventPid")`.
- Missing `parsed` is fine — we re-parse `raw` anyway.
"""

from __future__ import annotations

import asyncio
import json as _stdlib_json
import pathlib
from typing import TYPE_CHECKING, Any

from aionlslivetiming.events import Message, TimeSyncMessage
from aionlslivetiming.exceptions import (
    ReplayEmptyError,
    ReplayOrderingError,
    ReplaySchemaError,
)
from aionlslivetiming.logging import get_logger
from aionlslivetiming.parser import parse
from aionlslivetiming.transport.base import ClockOffset

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_log = get_logger("aionlslivetiming.transport.replay")


def _loads(raw: str | bytes) -> Any:
    """JSON decode; orjson if available, stdlib fallback (D-10)."""
    try:
        import orjson  # type: ignore[import-not-found]
        return orjson.loads(raw)
    except ImportError:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        return _stdlib_json.loads(raw)


class ReplayTransport:
    """Reads a JSONL log line-by-line and yields parsed :class:`Message` instances.

    Per D-14: ``ReplayTransport(path, *, speed_factor=1.0, suppress_time_sync=True)``.
    Per D-15: speed_factor=0 → burst (no sleeps); 1.0 → real-time; >1 → faster; <0 → ValueError.
    Per D-16: time-sync messages update ``clock_offset`` and are yielded only when
    ``suppress_time_sync=False`` (default True → consumer's ``__aiter__`` matches live).
    Per D-17: validation is loud on bad data:
      - Empty file → ReplayEmptyError
      - Missing `raw` → ReplaySchemaError(line_no)
      - Non-monotonic ts_recv_ms → ReplayOrderingError(line_no, prev, curr)
      - Invalid JSON trailing line → log WARNING once + skip (looks-done-but-isnt)

    Backward compat with D-07 (Phase 1): a JSONL with shape `{ts_recv_ms, raw}`
    is replayable; missing `event_pid` falls back to `raw.get("eventPid")`.
    """

    def __init__(
        self,
        path: str | pathlib.Path,
        *,
        speed_factor: float = 1.0,
        suppress_time_sync: bool = True,
    ) -> None:
        if speed_factor < 0:
            raise ValueError(f"speed_factor must be >= 0 (got {speed_factor})")
        self._path = pathlib.Path(path)
        self._speed_factor = float(speed_factor)
        self._suppress_time_sync = suppress_time_sync
        self._clock_offset = ClockOffset()
        self._connected = False

    @property
    def clock_offset(self) -> ClockOffset:
        """The clock-offset helper (D-04/D-16). Read by consumers to know server time."""
        return self._clock_offset

    @property
    def path(self) -> pathlib.Path:
        return self._path

    @property
    def speed_factor(self) -> float:
        return self._speed_factor

    @property
    def suppress_time_sync(self) -> bool:
        return self._suppress_time_sync

    async def connect(self) -> None:
        """Validate the file exists; do not open it yet (lazy on __aiter__)."""
        if not self._path.exists():
            raise FileNotFoundError(f"replay path does not exist: {self._path}")
        self._connected = True

    async def close(self) -> None:
        """No-op for ReplayTransport — the file handle closes per-iteration."""
        self._connected = False

    async def __aiter__(self) -> AsyncIterator[Message]:
        """Yield parsed Messages; honour speed_factor; validate ordering.

        Skips non-Message time-sync frames per `suppress_time_sync` (D-16).
        """
        if not self._connected:
            await self.connect()

        prev_ts: int | None = None
        prev_ts_for_sleep: int | None = None
        line_no = 0
        emitted_any = False
        warned_bad_line = False

        lines = await self._read_lines_async()
        for line_no, raw_payload, ts_recv_ms in lines:
            if ts_recv_ms is not None and prev_ts is not None and ts_recv_ms < prev_ts:
                raise ReplayOrderingError(
                    line_no=line_no, prev_ts=prev_ts, curr_ts=ts_recv_ms
                )
            if raw_payload is None:
                # Invalid JSON trailing line — WARNING once, skip
                if not warned_bad_line:
                    _log.warning("replay: skipping invalid JSON line at line %d", line_no)
                    warned_bad_line = True
                continue
            if "raw" not in raw_payload:
                raise ReplaySchemaError(
                    line_no=line_no, message=f"missing `raw` field at line {line_no}"
                )
            raw_msg = raw_payload["raw"]
            try:
                msg = parse(raw_msg)
            except Exception:
                # Parser refused — log WARNING once + skip
                if not warned_bad_line:
                    _log.warning("replay: parser raised at line %d, skipping", line_no)
                    warned_bad_line = True
                continue
            if isinstance(msg, TimeSyncMessage):
                # Update clock offset regardless of suppress flag (D-04)
                self._clock_offset.update(
                    server_time_ms=msg.value_ms,
                    local_recv_ms=int(asyncio.get_event_loop().time() * 1000),
                )
                if self._suppress_time_sync:
                    continue  # Do NOT yield time-sync (D-04 default)
            # Apply speed_factor (D-15): real-time vs burst vs faster.
            # Sleep BEFORE yielding the message so the first message is
            # emitted immediately on the first iteration (no prior delta).
            if (
                prev_ts_for_sleep is not None
                and ts_recv_ms is not None
                and self._speed_factor > 0
            ):
                delta_ms = ts_recv_ms - prev_ts_for_sleep
                if delta_ms > 0:
                    await asyncio.sleep((delta_ms / 1000.0) / self._speed_factor)
            if ts_recv_ms is not None:
                prev_ts_for_sleep = ts_recv_ms
            if ts_recv_ms is not None:
                prev_ts = ts_recv_ms
            emitted_any = True
            yield msg

        if not emitted_any:
            raise ReplayEmptyError(f"replay JSONL is empty: {self._path}")

    async def _read_lines_async(self) -> list[tuple[int, dict[str, Any] | None, int | None]]:
        """Read the JSONL file in a thread executor; return (line_no, dict_or_None, ts_or_None)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_lines_sync)

    def _read_lines_sync(self) -> list[tuple[int, dict[str, Any] | None, int | None]]:
        """Blocking line reader — runs in a thread executor.

        Returns a list so the async generator above can iterate from it
        without holding the file handle across awaits (which would block
        the loop on slow disks).
        """
        result: list[tuple[int, dict[str, Any] | None, int | None]] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line_no, raw_line in enumerate(fh, start=1):
                stripped = raw_line.rstrip("\n")
                if not stripped.strip():
                    continue  # blank line — skip silently
                try:
                    obj = _loads(stripped)
                except Exception:
                    result.append((line_no, None, None))
                    continue
                if not isinstance(obj, dict):
                    result.append((line_no, None, None))
                    continue
                ts = obj.get("ts_recv_ms")
                if ts is not None and not isinstance(ts, int):
                    try:
                        ts = int(ts)
                    except (TypeError, ValueError):
                        ts = None
                result.append((line_no, obj, ts))
        return result


__all__ = ["ReplayTransport"]
