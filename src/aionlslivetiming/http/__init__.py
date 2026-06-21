"""HTTP subpackage (Phase 3 optional fallback).

Currently exposes :func:`aionlslivetiming.http.laps_data.fetch_laps_data`
for the optional ``/event/{id}/laps-data`` REST drilldown. The primary
per-car-lap data source remains the WebSocket channel 7 subscription.
"""

from __future__ import annotations

from aionlslivetiming.http.laps_data import (
    DEFAULT_LAPS_DATA_BASE_URL,
    fetch_laps_data,
)

__all__ = ["DEFAULT_LAPS_DATA_BASE_URL", "fetch_laps_data"]
