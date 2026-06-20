"""One lap of a per-car lap drilldown (PID 7).

Lap records are immutable: the state reducer uses last-write-wins
semantics keyed by ``(session, starting_no, lap_no)``, so mutating an
existing ``LapRecord`` would be a bug — the cache always replaces the
whole record. ``frozen=True`` makes that intent explicit and lets
pydantic reject accidental mutation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LapRecord(BaseModel):
    """A single lap from a PID 7 per-car laps frame.

    All sector fields are optional because the server may emit a partial
    lap (e.g. a car retired mid-lap with only ``lap`` and ``time`` set).
    Extra server fields are preserved via ``extra="allow"`` to keep the
    round-trip stable across schema changes.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    lap_no: int
    time_ms: int
    s1_ms: int | None = None
    s2_ms: int | None = None
    s3_ms: int | None = None
