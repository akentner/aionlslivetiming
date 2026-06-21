"""nls-replay CLI — replay a recorded JSONL log via the public NLSClient API.

Per D-03..D-05 + D-25 (see 04-CONTEXT.md).

CLI surface:

- positional: ``<jsonl_path>``
- ``--speed N`` (float, default 1.0; 0 = burst, >1 = faster than real-time)
- ``--limit N`` (int; default unlimited — stop after N parsed messages)
- ``--show-time-sync`` (flag; default off — best-effort time-sync surface)
- ``--strict`` (flag; default off — raises on UnknownMessage /
  ReplaySchemaError / ReplayOrderingError)
- ``--summary`` (flag; default off — prints end-of-stream diagnostics)

Default mode is line-buffered stdout; suitable for piping to ``head`` /
``grep``. Exit code is 0 on normal completion (even when WARNING logs are
emitted). ``--strict`` flips this to 1 on any WARNING-level event.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import logging
import sys
from pathlib import Path
from typing import TextIO

from aionlslivetiming import NLSClient, ReplayError, UnknownEventError
from aionlslivetiming.events import UnknownMessage
from aionlslivetiming.logging import get_logger

__all__ = ["main", "run"]

_log = get_logger("aionlslivetiming.cli")


async def run(
    path: str | Path,
    *,
    speed_factor: float = 1.0,
    limit: int | None = None,
    show_time_sync: bool = False,
    strict: bool = False,
    summary: bool = False,
    out: TextIO | None = None,
) -> int:
    """Drive :meth:`NLSClient.from_replay` and print one line per Message.

    Returns 0 on normal completion; 1 if --strict and any error logged at
    WARNING. The ``out`` kwarg is for tests; default is ``sys.stdout``.

    Pre-scans the JSONL once (only when ``summary=True``) to compute
    first/last ``ts_recv_ms`` for the summary block. This is one extra
    disk read but acceptable for diagnostics mode.
    """
    out = out if out is not None else sys.stdout
    pid_counts: dict[int, int] = collections.Counter()
    unknown_count = 0
    emitted = 0
    # Pre-scan summary data (D-05)
    ts_first_ms: int | None = None
    ts_last_ms: int | None = None
    if summary:
        try:
            with Path(path).open("r", encoding="utf-8") as fh:  # noqa: ASYNC230
                for raw_line in fh:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        import orjson

                        obj = orjson.loads(stripped)
                    except ImportError:
                        import json as _stdlib_json

                        obj = _stdlib_json.loads(stripped)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    ts = obj.get("ts_recv_ms")
                    if isinstance(ts, int):
                        if ts_first_ms is None:
                            ts_first_ms = ts
                        ts_last_ms = ts
        except OSError as exc:
            _log.warning("replay: could not pre-scan %s: %s", path, exc)

    try:
        async with NLSClient.from_replay(path, speed_factor=speed_factor) as client:
            async for msg in client.messages():
                pid = getattr(msg, "event_pid", -1)
                pid_counts[pid] += 1
                if isinstance(msg, UnknownMessage):
                    unknown_count += 1
                    _log.warning(
                        "replay: UnknownMessage event_pid=%s raw_keys=%s",
                        pid,
                        list(getattr(msg, "raw", {}).keys()),
                    )
                    if strict:
                        # D-25: --strict raises UnknownEventError for
                        # UnknownMessage; transport-level ReplaySchemaError
                        # and ReplayOrderingError are re-raised by the
                        # transport and caught below.
                        raise UnknownEventError(
                            f"--strict: UnknownMessage at pid={pid}"
                        )
                out.write(repr(msg) + "\n")
                emitted += 1
                if limit is not None and emitted >= limit:
                    break

            # Optional time-sync stream (D-04). ReplayTransport suppresses
            # time-sync frames by default; the client iterator returns
            # nothing in that case. Best-effort — no warning is emitted
            # because suppression is the documented default.
            if show_time_sync:
                async for ts in client.time_sync():
                    out.write(repr(ts) + "\n")

    except ReplayError as exc:
        # ReplayEmptyError / ReplaySchemaError / ReplayOrderingError (D-25)
        _log.warning("replay: %s", exc)
        if strict:
            return 1
    except UnknownEventError as exc:
        # --strict mode raised on an UnknownMessage (D-25); user-facing
        # WARNING already emitted above; bubble out as exit 1.
        _log.warning("replay: %s", exc)
        return 1

    if summary:
        first_str = "n/a" if ts_first_ms is None else str(ts_first_ms)
        last_str = "n/a" if ts_last_ms is None else str(ts_last_ms)
        out.write("\n--- nls-replay summary ---\n")
        out.write(f"total messages: {emitted}\n")
        out.write(f"per eventPid: {dict(sorted(pid_counts.items()))}\n")
        out.write(f"first ts_recv_ms: {first_str}\n")
        out.write(f"last ts_recv_ms: {last_str}\n")
        out.write(f"UnknownMessage count: {unknown_count}\n")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Parses args and delegates to :func:`run`."""
    parser = argparse.ArgumentParser(
        prog="nls-replay",
        description="Replay a recorded NLS JSONL log via the NLSClient public API.",
    )
    parser.add_argument("jsonl_path", help="Path to the recorded JSONL file.")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (0 = burst, 1.0 = real-time, >1 = faster).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N parsed messages (default: unlimited).",
    )
    parser.add_argument(
        "--show-time-sync",
        action="store_true",
        default=False,
        help="Also emit TimeSyncMessage frames (replay-mode best-effort).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 on any parser warning (UnknownMessage / schema error).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=False,
        help="Print end-of-stream diagnostics (total / per-pid / ts range).",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    return asyncio.run(
        run(
            path=args.jsonl_path,
            speed_factor=args.speed,
            limit=args.limit,
            show_time_sync=args.show_time_sync,
            strict=args.strict,
            summary=args.summary,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
