"""Typed event messages emitted by the parser.

In Phase 1 this module is a stub: the public :data:`Message` alias points
to :class:`object` as a placeholder until the eight frozen ``@dataclass``
variants land in Plan 02.

Real ``Message`` union is added in Plan 02 once the 8 frozen dataclasses
exist (D-01, D-06). At that point ``Message`` becomes::

    Message = Union[
        InitialStateMessage,
        TrackStateMessage,
        RaceMessage,
        PerCarLapsMessage,
        QualifyingMessage,
        StatisticsMessage,
        TimeSyncMessage,
        UnknownMessage,
    ]
"""

from __future__ import annotations

# Placeholder until the eight dataclasses land in Plan 02.
# Real Message union is added in Plan 02 once the 8 frozen dataclasses exist.
Message = object

__all__ = ["Message"]
