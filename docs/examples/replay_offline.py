"""Replay offline example.

Loads a recorded JSONL log via the :class:`NLSClient` public API and prints a
summary of the cached state at end-of-stream.

Usage:
    uv run python examples/replay_offline.py /path/to/recording.jsonl

Expected output:
    Replay: N messages from /path/to/recording.jsonl (source=REPLAY)
    State freshness: FRESH
    Cars cached: M
    Track: <track state>

Capturing your own recording:
    ``uv run nls-record <event_id> /tmp/event.jsonl --max-seconds 3600``
    then point this example at the resulting JSONL. See ``docs/quickstart.md``
    for the full workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from aionlslivetiming import NLSClient, Source

__all__ = ["main"]


async def _run(path: Path) -> int:
    """Replay a JSONL file end-to-end and print a summary of the cached state."""
    async with NLSClient.from_replay(path) as client:
        assert client.source == Source.REPLAY
        count = 0
        async for _msg in client.messages():
            count += 1
        print(f"Replay: {count} messages from {path} (source={client.source.value})")
        print(f"State freshness: {client.state.freshness.value}")
        print(f"Cars cached: {len(client.state.cars)}")
        print(f"Track: {client.state.track}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a POSIX exit code (``2`` on file-not-found)."""
    parser = argparse.ArgumentParser(
        prog="replay_offline",
        description="Replay a recorded JSONL log and report cached state.",
    )
    parser.add_argument(
        "jsonl_path",
        type=Path,
        help="Path to a recorded JSONL file.",
    )
    args = parser.parse_args(argv)
    if not args.jsonl_path.exists():
        print(f"File not found: {args.jsonl_path}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args.jsonl_path))


if __name__ == "__main__":
    sys.exit(main())
