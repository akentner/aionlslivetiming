"""The :class:`RaceState` reducer — the write half of the cache.

``RaceState`` is a single in-memory cache mutated by :meth:`apply`.
The contract:

- **Single-writer.** The caller (the consumer's asyncio task) is
  responsible for not racing two ``apply()`` calls. The class does
  not lock.
- **Idempotent.** Applying the same :class:`Message` twice yields
  structurally equal state. The dedupe strategy depends on the
  message type — see each private ``_apply_*`` method.
- **Never raises.** Per D-03 a malformed message is dropped, not
  raised. ``apply()`` returns ``None`` on success and on drop.
- **Forward-compat.** :class:`aionlslivetiming.events.TimeSyncMessage`
  and :class:`aionlslivetiming.events.UnknownMessage` are no-ops
  (the former is a heartbeat, the latter is a placeholder for future
  server PIDs).

The read surface exposes plain Python types: dicts of
:class:`~aionlslivetiming.state.car.CarState`, tuples of
:class:`~aionlslivetiming.events.RaceMessage`, sorted lists of
:class:`~aionlslivetiming.state.lap.LapRecord`, and so on. No locks,
no asyncio — consumers read in the same task they write.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from aionlslivetiming.events import (
    InitialStateMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    RaceMessage,
    StatisticsMessage,
    TrackStateMessage,
)
from aionlslivetiming.state.car import CarState
from aionlslivetiming.state.enums import Freshness, Source
from aionlslivetiming.state.lap import LapRecord
from aionlslivetiming.state.track import TrackState

if TYPE_CHECKING:
    from collections.abc import Iterable

    from aionlslivetiming.state.filter import Filter


class RaceState:
    """In-memory race cache. Idempotent :meth:`apply`. Single-writer contract."""

    def __init__(self, *, source: Source = Source.LIVE) -> None:
        self._source: Source = source
        self._freshness: Freshness = Freshness.RESYNCING
        self._last_update_ms: int | None = None
        self._cars: dict[int, CarState] = {}
        self._track: TrackState | None = None
        self._track_name: str | None = None
        self._session: Any = None  # SessionInfo from events
        self._ver: str | None = None
        self._export_id: str | None = None
        self._messages: tuple[RaceMessage, ...] = ()
        self._seen_message_keys: set[tuple[str, str | None, int | None, str | None]] = set()
        self._laps: dict[tuple[str, int, int], LapRecord] = {}
        self._qualifying: tuple[Any, ...] = ()
        self._stats_leading: tuple[Any, ...] = ()
        self._stats_best_laps: tuple[Any, ...] = ()
        self._stats_best_sectors: dict[tuple[int, int], int] = {}

    # ------------------------------------------------------------------ reads
    @property
    def source(self) -> Source:
        return self._source

    @property
    def freshness(self) -> Freshness:
        return self._freshness

    @property
    def last_update_ms(self) -> int | None:
        return self._last_update_ms

    @property
    def cars(self) -> dict[int, CarState]:
        # Defensive copy so callers cannot mutate internal state.
        return dict(self._cars)

    @property
    def track(self) -> TrackState | None:
        return self._track

    @property
    def track_name(self) -> str | None:
        return self._track_name

    @property
    def ver(self) -> str | None:
        return self._ver

    @property
    def export_id(self) -> str | None:
        return self._export_id

    @property
    def session(self) -> Any:
        return self._session

    @property
    def messages(self) -> tuple[RaceMessage, ...]:
        return self._messages

    @property
    def qualifying(self) -> tuple[Any, ...]:
        return self._qualifying

    @property
    def stats_leading(self) -> tuple[Any, ...]:
        return self._stats_leading

    @property
    def stats_best_laps(self) -> tuple[Any, ...]:
        return self._stats_best_laps

    @property
    def stats_best_sectors(self) -> dict[tuple[int, int], int]:
        return dict(self._stats_best_sectors)

    def laps(self, starting_no: int, *, session: str | None = None) -> list[LapRecord]:
        """Return :class:`LapRecord` list for one car, sorted by ``lap_no``.

        If ``session`` is provided, only laps for that session are
        returned. Otherwise laps from all sessions for the same car are
        merged and sorted.
        """
        if session is None:
            return sorted(
                (lap for (_, no, _), lap in self._laps.items() if no == starting_no),
                key=lambda lr: lr.lap_no,
            )
        return sorted(
            (
                lap
                for (s, no, _), lap in self._laps.items()
                if s == session and no == starting_no
            ),
            key=lambda lr: lr.lap_no,
        )

    def standings(self) -> list[CarState]:
        """Cars ordered by ``position`` (None positions last)."""
        return sorted(
            self._cars.values(),
            key=lambda c: (c.position is None, c.position if c.position is not None else 0),
        )

    # -------------------------------------------------------------- filter DSL
    def filter(self) -> Filter:
        """Return a composable Filter over this state's cars.

        Builder-pattern API for queries — each method narrows the
        working set, and ``.cars()`` materialises the result. See
        :class:`~aionlslivetiming.state.filter.Filter` for the full
        DSL.
        """
        # Local import to avoid a circular dependency: filter.py
        # imports ``RaceState`` under TYPE_CHECKING only, but the
        # runtime path keeps the dependency direction clean.
        from aionlslivetiming.state.filter import Filter

        return Filter(self)

    def cars_by_class(self, class_name: str) -> list[CarState]:
        """Convenience pass-through: all cars whose ``class_name == class_name``."""
        return self.filter().by_class(class_name).cars()

    def cars_by_starting_no(self, value: int | Iterable[int]) -> list[CarState]:
        """Convenience pass-through: cars whose ``starting_no`` is in ``value``."""
        return self.filter().by_starting_no(value).cars()

    def top(self, n: int) -> list[CarState]:
        """Convenience pass-through: top ``n`` cars by position."""
        return self.filter().top(n).cars()

    # -------------------------------------------------------------- persistence
    def to_json(self) -> str:
        """Export the full state to a JSON string. Round-trip safe with :meth:`from_json`.

        STATE-06. Stdlib json — no orjson dep, this path is user-initiated.
        """
        from aionlslivetiming.state.persistence import to_json as _to_json

        return _to_json(self)

    def import_json(self, s: str) -> None:
        """Replace this state's contents with the deserialized snapshot.

        STATE-07. Raises :class:`ValueError` on malformed JSON.
        Idempotency-key set is rebuilt so re-applying an already-stored
        :class:`~aionlslivetiming.events.RaceMessage` does not duplicate
        it (D-PERSIST-3).
        """
        from aionlslivetiming.state.persistence import from_json as _from_json

        new_state = _from_json(s)
        self._source = new_state._source
        self._freshness = new_state._freshness
        self._last_update_ms = new_state._last_update_ms
        self._cars = new_state._cars
        self._track = new_state._track
        self._track_name = new_state._track_name
        self._session = new_state._session
        self._ver = new_state._ver
        self._export_id = new_state._export_id
        self._messages = new_state._messages
        self._seen_message_keys = new_state._seen_message_keys
        self._laps = new_state._laps
        self._qualifying = new_state._qualifying
        self._stats_leading = new_state._stats_leading
        self._stats_best_laps = new_state._stats_best_laps
        self._stats_best_sectors = new_state._stats_best_sectors

    @classmethod
    def from_json(cls, s: str) -> RaceState:
        """Construct a new :class:`RaceState` from a JSON snapshot.

        STATE-07. Convenience classmethod that wraps the pure-function
        :func:`~aionlslivetiming.state.persistence.from_json`.
        """
        from aionlslivetiming.state.persistence import from_json as _from_json

        return _from_json(s)

    # -------------------------------------------------------------- mutators
    def set_source(self, source: Source) -> None:
        """Update the :class:`Source` label (e.g. ``LIVE`` → ``REPLAY``)."""
        self._source = source

    def apply(self, msg: Any) -> None:
        """Reduce one :class:`Message` into the cache.

        Idempotent: applying the same message twice produces the same
        state. :class:`TimeSyncMessage` and :class:`UnknownMessage` are
        forward-compat no-ops. Malformed per-car-lap dicts are dropped
        per D-03 (never raise on bad server data).
        """
        self._last_update_ms = int(time.time() * 1000)
        if isinstance(msg, InitialStateMessage):
            self._apply_initial_state(msg)
        elif isinstance(msg, TrackStateMessage):
            self._apply_track_state(msg)
        elif isinstance(msg, RaceMessage):
            self._apply_race_message(msg)
        elif isinstance(msg, PerCarLapsMessage):
            self._apply_per_car_laps(msg)
        elif isinstance(msg, QualifyingMessage):
            self._qualifying = msg.results
        elif isinstance(msg, StatisticsMessage):
            self._apply_statistics(msg)
        # TimeSyncMessage, UnknownMessage: no-op (forward-compat / heartbeat)
        self._freshness = Freshness.FRESH

    def clear(self) -> None:
        """Empty all sub-caches and transition freshness to ``RESYNCING``."""
        self._cars.clear()
        self._track = None
        self._track_name = None
        self._session = None
        self._ver = None
        self._export_id = None
        self._messages = ()
        self._seen_message_keys.clear()
        self._laps.clear()
        self._qualifying = ()
        self._stats_leading = ()
        self._stats_best_laps = ()
        self._stats_best_sectors.clear()
        self._last_update_ms = None
        self._freshness = Freshness.RESYNCING

    # ---------------------------------------------------------- private apply
    def _apply_initial_state(self, msg: InitialStateMessage) -> None:
        self._track_name = msg.track_name
        self._session = msg.session
        self._ver = msg.ver
        self._export_id = msg.export_id
        # PID 0 is a "full reset" of cars per ARCHITECTURE.md line 226
        self._cars.clear()
        for r in msg.results:
            self._cars[r.starting_no] = CarState(
                starting_no=r.starting_no,
                position=r.position,
                class_name=r.class_name,
                driver=r.driver,
                laps_completed=r.laps,
                total_time_ms=r.total_time_ms,
                gap_to_leader_ms=r.gap_to_leader_ms,
                best_lap_ms=r.best_lap_ms,
            )

    def _apply_track_state(self, msg: TrackStateMessage) -> None:
        self._track = TrackState(
            track_state=msg.track_state,
            time_state=msg.time_state,
            tod_ms=msg.tod.value_ms if msg.tod else None,
            end_time_ms=msg.end_time.value_ms if msg.end_time else None,
        )

    def _apply_race_message(self, msg: RaceMessage) -> None:
        # Dedupe key: same text/category/starting_no/session is a duplicate.
        key = (msg.text, msg.category, msg.starting_no, msg.session)
        if key in self._seen_message_keys:
            return
        self._seen_message_keys.add(key)
        self._messages = (*self._messages, msg)

    def _apply_per_car_laps(self, msg: PerCarLapsMessage) -> None:
        for lap_dict in msg.laps:
            lap_no_raw = lap_dict.get("lap")
            time_raw = lap_dict.get("time")
            if lap_no_raw is None or time_raw is None:
                continue  # D-03: never raise on a malformed lap
            try:
                lap = LapRecord(
                    lap_no=int(lap_no_raw),
                    time_ms=int(time_raw),
                    s1_ms=int(lap_dict["s1"]) if lap_dict.get("s1") is not None else None,
                    s2_ms=int(lap_dict["s2"]) if lap_dict.get("s2") is not None else None,
                    s3_ms=int(lap_dict["s3"]) if lap_dict.get("s3") is not None else None,
                )
            except (TypeError, ValueError):
                continue  # D-03: never raise on a malformed lap
            # Last-write-wins keyed by (session, starting_no, lap_no)
            self._laps[(msg.session, msg.starting_no, lap.lap_no)] = lap

    def _apply_statistics(self, msg: StatisticsMessage) -> None:
        self._stats_leading = msg.leading
        self._stats_best_laps = msg.best_laps
        # sector_bests: keep the minimum value_ms per (starting_no, sector)
        for bs in msg.best_sectors:
            key = (bs.starting_no, bs.sector)
            existing = self._stats_best_sectors.get(key)
            if existing is None or bs.value_ms < existing:
                self._stats_best_sectors[key] = bs.value_ms
