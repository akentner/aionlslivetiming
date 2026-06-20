"""JSON snapshot persistence for :class:`~aionlslivetiming.state.RaceState`.

Pure functions: no class state, no I/O. The caller passes a
:class:`RaceState` and gets a JSON string (:func:`to_json`) or
vice-versa (:func:`from_json`).

Stdlib json only — no orjson dep. This path is user-initiated (export
/ import) not WS-hot-path, so stdlib performance is fine.

Schema versioning: every snapshot embeds a ``schema_version`` integer
at the top. Future STATE-06 iterations bump this constant and
:func:`from_json` raises with a helpful message. No migration logic in
v1 — just the version tag (D-PERSIST-2).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from aionlslivetiming.state.car import CarState
from aionlslivetiming.state.enums import Freshness, Source
from aionlslivetiming.state.lap import LapRecord
from aionlslivetiming.state.race_state import RaceState
from aionlslivetiming.state.track import TrackState

SCHEMA_VERSION = 1


def to_json(state: RaceState) -> str:
    """Serialize a :class:`RaceState` to a JSON string.

    Round-trip safe with :func:`from_json`. Embeds a ``schema_version``
    integer at the top so future versions can detect incompatible
    snapshots and raise with a helpful message.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": state.source.value,
        "freshness": state.freshness.value,
        "last_update_ms": state.last_update_ms,
        "track_name": state.track_name,
        "ver": state.ver,
        "export_id": state.export_id,
        "session": asdict(state._session) if state._session else None,
        "track": state.track.model_dump() if state.track else None,
        "cars": {str(no): car.model_dump() for no, car in state.cars.items()},
        "messages": [asdict(m) for m in state.messages],
        "laps": [
            {"session": s, "starting_no": no, "lap": lap.model_dump()}
            for (s, no, _lapno), lap in sorted(state._laps.items())
        ],
        "qualifying": [asdict(r) for r in state.qualifying],
        "stats_leading": [asdict(r) for r in state.stats_leading],
        "stats_best_laps": [asdict(r) for r in state.stats_best_laps],
        "stats_best_sectors": [
            {"starting_no": no, "sector": sec, "value_ms": v}
            for (no, sec), v in sorted(state.stats_best_sectors.items())
        ],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def from_json(s: str) -> RaceState:
    """Deserialize a JSON string (produced by :func:`to_json`) back into a RaceState.

    Raises :class:`ValueError` on malformed JSON, missing
    ``schema_version``, or unsupported version. Never silently returns
    an empty state — a corrupted import is a user error and should
    raise (D-PERSIST-5).
    """
    try:
        payload = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid state JSON: {e}") from e

    if not isinstance(payload, dict):
        raise ValueError("invalid state JSON: expected an object at the top level")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {version!r}; this build understands {SCHEMA_VERSION}"
        )

    state = RaceState(source=Source(payload["source"]))
    state._freshness = Freshness(payload["freshness"])
    state._last_update_ms = payload.get("last_update_ms")
    state._track_name = payload.get("track_name")
    state._ver = payload.get("ver")
    state._export_id = payload.get("export_id")

    # SessionInfo: reconstruct manually (no from_dict helper on stdlib dataclass)
    session_d = payload.get("session")
    if session_d is not None:
        from aionlslivetiming.events import SessionInfo

        state._session = SessionInfo(**session_d)

    track_d = payload.get("track")
    if track_d is not None:
        state._track = TrackState.model_validate(track_d)

    # Cars: dict[str, dict] -> dict[int, CarState]
    cars_d = payload.get("cars") or {}
    state._cars = {
        int(no_str): CarState.model_validate(car_d) for no_str, car_d in cars_d.items()
    }

    # Messages: list[dict] -> tuple[RaceMessage, ...]; rebuild seen-keys for idempotency
    from aionlslivetiming.events import RaceMessage

    msgs: list[RaceMessage] = []
    seen: set[tuple[str, str | None, int | None, str | None]] = set()
    for m_d in payload.get("messages") or []:
        m = RaceMessage(**m_d)
        msgs.append(m)
        seen.add((m.text, m.category, m.starting_no, m.session))
    state._messages = tuple(msgs)
    state._seen_message_keys = seen

    # Laps: list[{session, starting_no, lap: dict}]
    # -> dict[(session, starting_no, lap_no), LapRecord]
    laps_d: dict[tuple[str, int, int], LapRecord] = {}
    for entry in payload.get("laps") or []:
        s_str = entry["session"]
        no = int(entry["starting_no"])
        lap = LapRecord.model_validate(entry["lap"])
        laps_d[(s_str, no, lap.lap_no)] = lap
    state._laps = laps_d

    # Qualifying / stats_leading / stats_best_laps: list[dict] -> tuple[CarResult, ...]
    from aionlslivetiming.events import CarResult

    state._qualifying = tuple(CarResult(**r) for r in (payload.get("qualifying") or []))
    state._stats_leading = tuple(CarResult(**r) for r in (payload.get("stats_leading") or []))
    state._stats_best_laps = tuple(CarResult(**r) for r in (payload.get("stats_best_laps") or []))

    # stats_best_sectors: list[{starting_no, sector, value_ms}] -> dict[(int, int), int]
    sector_d: dict[tuple[int, int], int] = {}
    for entry in payload.get("stats_best_sectors") or []:
        sector_d[(int(entry["starting_no"]), int(entry["sector"]))] = int(entry["value_ms"])
    state._stats_best_sectors = sector_d

    return state
