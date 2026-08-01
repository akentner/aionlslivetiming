"""Live-Tail für NLS Livetiming — verbindet sich und druckt Messages, sobald sie ankommen.

Usage:
    python3 examples/live_tail.py 20
    python3 examples/live_tail.py 20 --only results,track,messages
    python3 examples/live_tail.py 20 --write /tmp/race.jsonl    # zusätzlich mitschneiden
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from aionlslivetiming import NLSClient
from aionlslivetiming.events import (
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    StatisticsMessage,
    TrackStateMessage,
)


# Which PIDs to print. None = all.
PID_FILTER = {
    "results": lambda m: isinstance(m, InitialStateMessage),
    "track": lambda m: isinstance(m, TrackStateMessage),
    "messages": lambda m: isinstance(m, RaceMessage),
    "percar": lambda m: isinstance(m, PerCarLapsMessage),
    "qualifying": lambda m: isinstance(m, QualifyingMessage),
    "stats": lambda m: isinstance(m, StatisticsMessage),
}


def fmt_initial(msg: InitialStateMessage) -> str:
    return (
        f"RESULTS  ver={msg.ver}  export={msg.export_id}  "
        f"track={msg.track_name}  cars={len(msg.results)}  "
        f"heat={msg.session.heat if msg.session else '?'}  "
        f"cup={msg.session.cup if msg.session else '?'}"
    )


def fmt_track(msg: TrackStateMessage) -> str:
    tod = str(msg.tod) if msg.tod else "-"
    return (
        f"TRACK    state={msg.track_state}  time={msg.time_state}  "
        f"tod={tod}"
    )


def fmt_race(msg: RaceMessage) -> str:
    cat = msg.category or "?"
    car = f"#{msg.starting_no}" if msg.starting_no else ""
    return f"MESSAGE  [{cat}] {car} {msg.text[:70]}"


def fmt_percar(msg: PerCarLapsMessage) -> str:
    return f"PERCAR   session={msg.session}  car#{msg.starting_no}  laps={len(msg.laps)}"


def fmt_qualifying(msg: QualifyingMessage) -> str:
    rows = msg.results or []
    return f"QUALIFY  rows={len(rows)}"


def fmt_stats(msg: StatisticsMessage) -> str:
    return (
        f"STATS    leading={len(msg.leading or [])}  bestlaps={len(msg.best_laps or [])}  "
        f"bestsectors={len(msg.best_sectors or [])}"
    )


def fmt_state_snapshot(state, top_n: int = 5) -> str | None:
    """Top-N standings from cached state."""
    cars = list(state.cars.values())
    if not cars:
        return None
    positioned = [c for c in cars if c.position is not None]
    positioned.sort(key=lambda c: c.position)
    top = positioned[:top_n]
    lines = [f"  STANDINGS top {len(top)}/{len(cars)} cars"]
    lines.append(
        f"    {'POS':>3}  {'CAR':>4}  {'DRIVER':<24}  {'CLS':<6}  {'LAPS':>5}  {'BEST LAP':>10}"
    )
    for c in top:
        best = f"{c.best_lap_ms / 1000:.2f}s" if c.best_lap_ms else "-"
        driver = (c.driver or "?")[:24]
        lines.append(
            f"    {c.position or '-':>3}  {c.starting_no:>4}  {driver:<24}  "
            f"{(c.class_name or '?')[:6]:<6}  {c.laps_completed:>5}  {best:>10}"
        )
    return "\n".join(lines)


def format_msg(msg) -> str | None:
    if isinstance(msg, InitialStateMessage):
        return fmt_initial(msg)
    if isinstance(msg, TrackStateMessage):
        return fmt_track(msg)
    if isinstance(msg, RaceMessage):
        return fmt_race(msg)
    if isinstance(msg, PerCarLapsMessage):
        return fmt_percar(msg)
    if isinstance(msg, QualifyingMessage):
        return fmt_qualifying(msg)
    if isinstance(msg, StatisticsMessage):
        return fmt_stats(msg)
    return None


async def live_tail(event_id: str, only: list | None, write_jsonl: Path | None) -> None:
    print(f"Connecting to NLS event {event_id}...", flush=True)
    if write_jsonl is not None:
        write_jsonl.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl.unlink(missing_ok=True)
        f = write_jsonl.open("wb")
    else:
        f = None

    snapshot_every = 25
    since_snapshot = 0

    try:
        async with NLSClient(event_id=event_id) as client:
            print(
                f"  source={client.source.value}  freshness={client.state.freshness.value}  "
                f"cars={len(client.state.cars)}",
                flush=True,
            )
            print("-" * 80, flush=True)

            async for msg in client.messages():
                if only is not None and not any(filt(msg) for filt in only):
                    continue

                now_ms = int(time.time() * 1000)

                line = format_msg(msg)
                if line is None:
                    line = f"UNKNOWN  {type(msg).__name__}  pid={getattr(msg, 'event_pid', '?')}"
                print(f"{time.strftime('%H:%M:%S')}  {line}", flush=True)

                since_snapshot += 1
                if since_snapshot >= snapshot_every and client.state.cars:
                    snap = fmt_state_snapshot(client.state)
                    if snap:
                        print(snap, flush=True)
                    since_snapshot = 0
                    snapshot_every = min(60, snapshot_every + 5)

                if f is not None:
                    f.write((json.dumps({
                        "ts_recv_ms": now_ms,
                        "raw": dict(msg.raw),
                    }) + "\n").encode())
    except KeyboardInterrupt:
        print("\n(disconnected)", flush=True)
    finally:
        if f is not None:
            f.close()
            print(f"(also wrote to {write_jsonl})", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-tail NLS livetiming feed")
    parser.add_argument("event_id", help="NLS event id (e.g. 20)")
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated subset: results,track,messages,percar,qualifying,stats",
    )
    parser.add_argument("--write", type=Path, default=None, help="also write to JSONL file")
    args = parser.parse_args()

    only = None
    if args.only:
        only = [PID_FILTER[k] for k in args.only.split(",") if k in PID_FILTER]
        if not only:
            print(f"unknown --only subset: {args.only}", file=sys.stderr)
            sys.exit(1)

    try:
        asyncio.run(live_tail(args.event_id, only, args.write))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()