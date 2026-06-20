"""Track-state snapshot (one PID 4 apply).

Flattens the ``TimeOfDay`` dataclasses from ``TrackStateMessage`` into
plain ``int`` millisecond fields so consumers do not need to import
from ``aionlslivetiming.events``. Immutable: each new PID 4 frame
replaces the previous ``TrackState`` wholesale.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TrackState(BaseModel):
    """One PID 4 frame flattened to ms-valued primitives."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    track_state: str
    time_state: str
    tod_ms: int | None = None
    end_time_ms: int | None = None
