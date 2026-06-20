"""Unknown-message forward-compatibility fallback.

Per PROJECT.md "schema can change between seasons" pitfall, the parser
*never* crashes on a PID it does not recognise — it emits an
:class:`UnknownMessage` carrying the raw payload so downstream
consumers can still log it or surface it.

Unlike the other 7 classes, ``event_pid`` here is an *instance* field
(the actual PID value seen on the wire), not a ``ClassVar``, because
each unknown event has its own PID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class UnknownMessage:
    """Forward-compatibility fallback for unrecognised PIDs or payloads."""

    event_pid: int
    raw: Mapping[str, Any] = field(default_factory=dict)
