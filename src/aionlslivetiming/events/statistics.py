"""Statistics message (PID 9002).

PID 9002 frames carry aggregate race statistics: the current leader
(``LEADING``), overall best laps (``BEST_LAPS``), and best sectors
across all cars (``BEST_SECTORS``). Each of the three sub-tables
defaults to ``()`` so any subset of them being present parses
cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aionlslivetiming.events.common import BestSector, CarResult


@dataclass(frozen=True, slots=True)
class StatisticsMessage:
    """PID 9002: aggregate race statistics (leading, best laps, best sectors)."""

    event_pid: ClassVar[int] = 9002

    leading: tuple[CarResult, ...] = ()
    best_laps: tuple[CarResult, ...] = ()
    best_sectors: tuple[BestSector, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
