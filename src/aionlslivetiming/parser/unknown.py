"""Parser for unknown / unrecognised payloads.

The NLS server's schema is not versioned (PROJECT.md pitfall) and can
change between seasons. The dispatcher falls through to this parser
for any ``eventPid`` that does not match the 6 known channels.

The resulting :class:`UnknownMessage` carries the actual PID as an
instance field plus the full raw payload so consumers can log it,
surface it, or upgrade the parser to handle it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.unknown import UnknownMessage

__all__ = ["parse_unknown"]


def parse_unknown(raw: Any, event_pid: int) -> UnknownMessage:
    """Wrap an unrecognised payload in an :class:`UnknownMessage`.

    The WARNING log emission happens at the dispatcher level (the
    call to :func:`warn_missing`) so the dedupe set is keyed on the
    actual unknown PID. This function only does the construction.

    Non-Mapping payloads are stored verbatim so consumers can inspect
    them later.
    """
    if isinstance(raw, Mapping):
        stored = dict(raw)
    else:
        stored = {"_raw_non_mapping": raw}
    return UnknownMessage(event_pid=event_pid, raw=stored)
