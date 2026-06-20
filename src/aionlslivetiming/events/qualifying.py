"""Qualifying message (PID 501).

PID 501 frames carry the top-qualifying tables (pro and pro-am) as a
``RESULT`` array. Per-lap detail and intermediate splits are not
included; consumers wanting full per-driver history subscribe to PID 7.

``results`` defaults to ``()`` so a frame without a ``RESULT`` key
parses cleanly rather than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aionlslivetiming.events.common import CarResult


@dataclass(frozen=True, slots=True)
class QualifyingMessage:
    """PID 501: top-qualifying table."""

    event_pid: ClassVar[int] = 501

    results: tuple[CarResult, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
