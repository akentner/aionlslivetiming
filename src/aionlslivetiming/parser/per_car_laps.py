"""Parser for PID 7 (per-car laps).

Maps the NLS server's PID 7 payload (``session``, ``startingNo``,
``laps``) onto :class:`PerCarLapsMessage`. Per D-03 individual lap
dicts are preserved verbatim in the ``laps`` tuple — typed lap
parsing is Phase 2 (state cache) work.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aionlslivetiming.events.per_car_laps import PerCarLapsMessage
from aionlslivetiming.parser._helpers import _opt_int, _opt_str, warn_missing

__all__ = ["parse_pid_7"]

_EVENT_PID = 7


def parse_pid_7(raw: Mapping[str, Any]) -> PerCarLapsMessage:
    """Parse a PID 7 payload into a :class:`PerCarLapsMessage`.

    PID 7 only carries meaningful data when the client subscribed with
    an explicit ``{session, startingNo}`` handshake — otherwise the
    server returns empty frames. We accept both modern
    (``startingNo``/``session``) and older (``STNR``/``SESSION``) key
    names without warning when the payload is just an empty
    keep-alive frame.
    """
    starting_no = _opt_int(raw.get("startingNo") or raw.get("STNR")) or 0
    session = _opt_str(raw.get("session") or raw.get("SESSION")) or ""

    if not starting_no:
        warn_missing("startingNo", _EVENT_PID)
    if not session:
        warn_missing("session", _EVENT_PID)

    laps_raw = raw.get("laps") or ()
    return PerCarLapsMessage(
        session=session,
        starting_no=starting_no,
        laps=tuple(dict(lap) for lap in laps_raw if isinstance(lap, Mapping)),
        raw=dict(raw),
    )
