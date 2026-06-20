"""Live-capture JSONL logger CLI (D-07).

This module is the very first deliverable of Phase 1. It connects to the
production NLS livetiming WebSocket at ``wss://livetiming.azurewebsites.net/``,
sends the initial handshake JSON, and appends every received WebSocket frame
to a JSONL file. Each line has the shape ``{"ts_recv_ms": <int>, "raw": <obj>}``
— a strict subset of the Phase 2 recorder schema
``{"ts_recv_ms", "event_pid", "raw", "parsed"}``.

It does not parse the payload, does not maintain any state, and exits cleanly
on Ctrl-C or remote close. The captured JSONL is the seed material for the
hand-crafted parser fixtures in Plan 02 (D-08).

Run it as a module::

    python -m aionlslivetiming.cli.jsonl_logger --help
"""

from __future__ import annotations

import argparse
import asyncio
import json as _stdlib_json
import logging
import pathlib
import time
from typing import TYPE_CHECKING, Any

from aionlslivetiming.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

__all__ = ["main", "run"]

_log = get_logger("aionlslivetiming.cli")

#: Default host for the live NLS livetiming WebSocket.
#: The endpoint lives at the root path (verified via WS sniff against
#: ``https://livetiming.azurewebsites.net/events/{id}/results/`` and matching
#: the JS bundle's ``factory("".concat(protocol, "://", host))`` pattern).
DEFAULT_HOST: str = "wss://livetiming.azurewebsites.net/"

#: Default channel IDs (PIDs) the client subscribes to via the ``eventPid``
#: handshake array. Matches the JS bundle's default for the leaderboard view:
#: 0 = initial state, 4 = track state, 7 = per-car laps, 501 = qualifying,
#: 9002 = statistics, 3 = race messages. Override with ``--channels``.
DEFAULT_CHANNELS: tuple[int, ...] = (0, 3, 4, 7, 501, 9002)


def _json_dumps(obj: Any) -> str:
    """Serialize *obj* to JSON text.

    Prefers :mod:`orjson` for speed; falls back to :mod:`json` if orjson is
    not installed (orjson is an optional extra per D-10).
    """
    try:
        import orjson  # type: ignore[import-not-found]

        result: str = orjson.dumps(obj).decode("utf-8")
    except ImportError:
        result = _stdlib_json.dumps(obj, separators=(",", ":"))
    return result


def _json_loads(raw: str | bytes | bytearray) -> Any:
    """Deserialize JSON text/bytes.

    Prefers :mod:`orjson`; falls back to :mod:`json` if not installed.
    """
    try:
        import orjson  # type: ignore[import-not-found,unused-ignore]

        result: Any = orjson.loads(raw)
    except ImportError:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        result = _stdlib_json.loads(raw)
    return result


async def run(
    event_id: str,
    output_path: str | pathlib.Path,
    *,
    host: str = DEFAULT_HOST,
    channels: Sequence[int] = DEFAULT_CHANNELS,
    max_seconds: float | None = None,
    websockets_factory: Callable[..., Awaitable[Any]] | None = None,
) -> int:
    """Connect to the NLS livetiming WebSocket and dump frames to *output_path*.

    Parameters
    ----------
    event_id:
        Event identifier sent in the initial handshake JSON (as a string,
        matching the JS bundle's ``{"eventId": "<id>"}`` contract).
    output_path:
        Destination JSONL file. The file is overwritten if it already exists.
    host:
        WebSocket base URL. Defaults to the production NLS endpoint at the
        root path (verified by WS sniff).
    channels:
        Sequence of channel IDs (``eventPid`` values) to subscribe to in the
        handshake. Each ID selects one NLS multiplex channel: 0 = initial
        state, 3 = race messages, 4 = track state, 7 = per-car laps,
        501 = qualifying, 9002 = statistics.
    max_seconds:
        If set, stop capturing after this many seconds and return ``0``.
    websockets_factory:
        Optional override for ``websockets.connect`` (used in tests).
        When ``None``, the real ``websockets`` module is imported lazily
        inside this coroutine so test code can monkeypatch
        ``aionlslivetiming.cli.jsonl_logger.websockets``.

    Returns
    -------
    int
        Process exit code. ``0`` on success, normal termination, Ctrl-C or
        remote close.
    """
    if websockets_factory is None:
        import websockets

        # Real ``websockets.connect`` is itself a coroutine function — just
        # bind it directly. Test code can pass its own ``websockets_factory``
        # (typically a sync callable that returns a coroutine wrapping a
        # context manager) for the no-network path.
        connect: Callable[..., Awaitable[Any]] = websockets.connect
    else:
        connect = websockets_factory

    url = host.rstrip("/") + "/"
    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    deadline: float | None = time.monotonic() + max_seconds if max_seconds is not None else None

    _log.info("connecting to %s for event %s (channels=%s)", url, event_id, list(channels))

    try:
        async with await connect(url, open_timeout=10, ping_interval=20, ping_timeout=20) as ws:
            # Initial handshake — matches the JS bundle's onopen send:
            # ``{"eventId":"<id>","eventPid":[<channels>],"clientLocalTime":<ms>}``.
            handshake = _json_dumps(
                {
                    "eventId": str(event_id),
                    "eventPid": list(channels),
                    "clientLocalTime": int(time.time() * 1000),
                }
            )
            await ws.send(handshake)
            _log.info("handshake sent, capturing frames to %s", out)

            with out.open("w", encoding="utf-8") as fh:  # noqa: ASYNC230
                # ASYNC230: blocking file open is fine for a CLI capture loop
                # that runs until the user hits Ctrl-C. The file write is one
                # line per WS frame, sub-millisecond; the blocking recv() call
                # dominates latency by 1000x. We deliberately avoid pulling
                # in aiofiles for this single-purpose tool.
                try:
                    while True:
                        if deadline is not None and time.monotonic() >= deadline:
                            _log.info("max_seconds reached, stopping")
                            return 0

                        # Race ``recv()`` against the remaining deadline so a
                        # quiet server does not block the CLI past ``max_seconds``.
                        # We use ``asyncio.wait_for`` because the ``websockets``
                        # library's ``recv()`` does not accept a ``timeout``
                        # kwarg (the deadline-aware pattern is ``wait_for``).
                        recv_timeout = (
                            max(0.0, deadline - time.monotonic())
                            if deadline is not None
                            else None
                        )
                        try:
                            if recv_timeout is not None:
                                raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                            else:
                                raw = await ws.recv()
                        except TimeoutError:
                            if deadline is not None and time.monotonic() >= deadline:
                                _log.info("max_seconds reached, stopping")
                                return 0
                            # Spurious timeout from underlying transport —
                            # loop and let the deadline check decide.
                            continue
                        payload = _json_loads(raw)
                        line = {
                            "ts_recv_ms": int(time.time() * 1000),
                            "raw": payload,
                        }
                        fh.write(_json_dumps(line) + "\n")
                except KeyboardInterrupt:
                    _log.info("interrupted by user, exiting cleanly")
                    return 0
                except Exception as exc:
                    # websockets.exceptions.ConnectionClosed and other transport
                    # shutdown signals land here. Treat as normal end-of-stream.
                    _log.info("connection closed: %s", exc)
                    return 0
    except KeyboardInterrupt:
        _log.info("interrupted by user before connection, exiting cleanly")
        return 0
    except Exception as exc:
        # ``websockets.exceptions.ConnectionClosed`` raised from the factory
        # itself (before ``__aenter__`` returns) lands here.
        _log.info("connection failed: %s", exc)
        return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Parses args and delegates to :func:`run`."""
    parser = argparse.ArgumentParser(
        prog="aionlslivetiming.cli.jsonl_logger",
        description=(
            "Connect to the NLS livetiming WebSocket and dump every received "
            "frame to a JSONL file. Used to capture real session data for "
            "parser fixtures (Phase 1, D-07)."
        ),
    )
    parser.add_argument(
        "event_id",
        help="Event identifier (sent in the handshake JSON).",
    )
    parser.add_argument(
        "output",
        help="Destination JSONL file (overwritten if it exists).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"WebSocket base URL (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--channels",
        default=",".join(str(c) for c in DEFAULT_CHANNELS),
        help=(
            "Comma-separated channel IDs to subscribe to via the eventPid "
            f"handshake (default: {','.join(str(c) for c in DEFAULT_CHANNELS)})."
        ),
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Stop capturing after N seconds (default: run until interrupted).",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    channels = tuple(int(c.strip()) for c in args.channels.split(",") if c.strip())

    return asyncio.run(
        run(
            event_id=args.event_id,
            output_path=args.output,
            host=args.host,
            channels=channels,
            max_seconds=args.max_seconds,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
