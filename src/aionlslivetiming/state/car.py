"""Per-car state (one car in a RaceState).

``CarState`` is the value type held in ``RaceState.cars`` keyed by
``starting_no``. It is *not* frozen — the reducer mutates
``sector_bests`` in-place when a new best arrives, so ``frozen=False``
is required. Single-writer access is the caller's responsibility
(ARCHITECTURE.md line 168: state/ is mutated from one asyncio task).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CarState(BaseModel):
    """One car: position, lap count, gaps, best lap, and a sector-bests map.

    ``sector_bests`` is a ``dict[int, int]`` mapping sector number to
    value in milliseconds; the reducer keeps only the best (lowest) per
    sector. ``model_config`` allows extra fields so unknown server
    fields surface in the dump without crashing the parser.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=False)

    starting_no: int
    position: int | None = None
    class_name: str | None = None
    driver: str | None = None
    laps_completed: int = 0
    total_time_ms: int | None = None
    gap_to_leader_ms: int | None = None
    best_lap_ms: int | None = None
    sector_bests: dict[int, int] = Field(default_factory=dict)
