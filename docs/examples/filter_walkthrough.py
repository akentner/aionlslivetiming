"""Filter walkthrough example.

Loads the bundled sample JSONL, populates the cached state, then exercises
each of the 6 filter dimensions from FILT-01..06.

Usage:
    uv run python examples/filter_walkthrough.py

Expected output:
    Filter walkthrough (6 dimensions):
    - by_class('SP9'):         N cars
    - by_starting_no(101):     N cars
    - by_driver('Smith'):      N cars
    - by_position(lo=1, hi=3): N cars
    - by_lap(lo=10):           N cars
    - by_sector_time_lt(sector=1, value_ms=90000): N cars

The exact numbers depend on the contents of ``sample_event.jsonl`` — they
demonstrate that each filter dimension can be exercised against the bundled
fixture without network access. ``by_sector_time_lt`` may report ``0 cars``
because per-car ``sector_bests`` are populated by per-car-laps (PID 7)
frames, which the bundled sample does not include — the filter still
demonstrates the API and a live replay with PID 7 traffic will populate it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from aionlslivetiming import NLSClient

__all__ = ["main"]


async def _run(sample: Path) -> int:
    """Replay the bundled sample JSONL, then exercise each filter dimension."""
    async with NLSClient.from_replay(sample) as client:
        # Drain the stream so state is populated before we query it.
        async for _msg in client.messages():
            pass
        state = client.state
        print("Filter walkthrough (6 dimensions):")
        print(
            f"- by_class('SP9'): "
            f"{len(state.filter().by_class('SP9').cars())} cars"
        )
        print(
            f"- by_starting_no(101): "
            f"{len(state.filter().by_starting_no(101).cars())} cars"
        )
        print(
            f"- by_driver('Smith'): "
            f"{len(state.filter().by_driver('Smith').cars())} cars"
        )
        print(
            f"- by_position(lo=1, hi=3): "
            f"{len(state.filter().by_position(min=1, max=3).cars())} cars"
        )
        print(
            f"- by_lap(lo=10): "
            f"{len(state.filter().by_lap(min=10).cars())} cars"
        )
        print(
            f"- by_sector_time_lt(sector=1, value_ms=90000): "
            f"{len(state.filter().sector_time_lt(sector=1, value_ms=90000).cars())} cars"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a POSIX exit code."""
    sample = Path(__file__).resolve().parent / "data" / "sample_event.jsonl"
    return asyncio.run(_run(sample))


if __name__ == "__main__":
    sys.exit(main())
