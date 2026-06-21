"""Live quickstart example.

Connects to a live NLS race and prints a snapshot of cached state every 30 seconds.

Usage:
    # Real run (needs network + a valid event_id):
    uv run python examples/live_quickstart.py YOUR_EVENT_ID

    # CI mode (no network; uses the bundled sample):
    uv run python examples/live_quickstart.py --dry-run

Expected output (real run):
    Connected to event YOUR_EVENT_ID (source=LIVE)
    Streaming messages...
    After 30s: N messages, M cars in state, track=GREEN

Expected output (dry run):
    Dry run: 6 messages from sample, 3 cars in state, track=CHEQUERED

Finding an event_id:
    Visit https://livetiming.azurewebsites.net/ during a race weekend; the
    current event id appears in the URL of the live timing page (an integer,
    e.g. ``20`` for the most recent NLS round).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from aionlslivetiming import NLSClient, Source

__all__ = ["main"]


async def _run_live(event_id: str, duration_s: float) -> int:
    """Connect to a live race, stream messages for ``duration_s``, report state."""
    async with NLSClient(event_id=event_id) as client:
        assert client.source == Source.LIVE
        print(f"Connected to event {event_id} (source={client.source.value})")
        print("Streaming messages...")
        count = 0
        try:
            end_at = asyncio.get_event_loop().time() + duration_s
            while asyncio.get_event_loop().time() < end_at:
                # Drain messages until either 30s elapsed or the budget is exhausted.
                remaining = end_at - asyncio.get_event_loop().time()

                async def _drain() -> None:
                    nonlocal count
                    async for _msg in client.messages():
                        count += 1

                try:
                    await asyncio.wait_for(_drain(), timeout=min(30.0, remaining))
                except TimeoutError:
                    # End of the 30s window — print a snapshot and continue.
                    print(
                        f"After {duration_s - remaining:.0f}s: {count} messages, "
                        f"{len(client.state.cars)} cars in state, "
                        f"track={client.state.track}"
                    )
        except TimeoutError:
            pass
        print(
            f"After {duration_s}s: {count} messages, "
            f"{len(client.state.cars)} cars in state, "
            f"track={client.state.track}"
        )
    return 0


async def _run_dry(sample: Path) -> int:
    """CI mode: drive ``NLSClient.from_replay`` against the bundled sample JSONL.

    No network — uses the same fixture that powers ``filter_walkthrough.py``
    and the test suite so CI never depends on the NLS server.
    """
    async with NLSClient.from_replay(sample) as client:
        count = 0
        async for _msg in client.messages():
            count += 1
        print(
            f"Dry run: {count} messages from sample, "
            f"{len(client.state.cars)} cars in state, "
            f"track={client.state.track}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a POSIX exit code."""
    parser = argparse.ArgumentParser(
        prog="live_quickstart",
        description="Connect to a live NLS race and stream messages.",
    )
    parser.add_argument(
        "event_id",
        nargs="?",
        default="YOUR_EVENT_ID",
        help="NLS event id (e.g. '20'). Use --dry-run for CI mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against the bundled sample JSONL instead of the live server.",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=30.0,
        help="How long to stream in seconds (default 30s).",
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        sample = (
            Path(__file__).resolve().parent.parent
            / "tests"
            / "fixtures"
            / "example_messages.jsonl"
        )
        return asyncio.run(_run_dry(sample))
    return asyncio.run(_run_live(args.event_id, args.duration_s))


if __name__ == "__main__":
    sys.exit(main())
