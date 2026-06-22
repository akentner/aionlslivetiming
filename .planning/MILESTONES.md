# Milestones

## v0.1.0 AIO NLS Livetiming MVP (Shipped: 2026-06-22)

**Phases completed:** 4 phases, 16 plans, 26 tasks

**Key accomplishments:**

- Installable src-layout Python package (hatchling + py.typed) with D-07 live-capture JSONL CLI and pytest-asyncio test harness — all 10 tests green, ruff + mypy clean.
- Frozen `@dataclass(slots=True)` event types for all 8 NLS server channels (PIDs 0/3/4/7/501/9002 + time-sync + unknown), plus 11 hand-crafted fixture JSONs as the public parser-test contract — 22 tests green, ruff + mypy strict clean.
- `parse()` dispatcher over 6 NLS PIDs with type-discriminated time-sync branch, UnknownMessage forward-compat fallback, and ≥80% coverage gate — 92 tests pass, parser/+events/ coverage is 92%.
- Idempotent in-memory race cache that turns the 7 typed Messages (TimeSync + Unknown are no-ops) into a queryable, freshness-tracked state — pydantic value models + stdlib Source/Freshness enums + single-writer apply() contract.
- Composable query object over `RaceState.cars` that exposes six independent filter dimensions (`by_class` / `by_starting_no` / `by_driver` / `by_position` / `by_lap` / `sector_time_lt`) which AND-combine into one query result, plus convenience pass-throughs on `RaceState` for the FastF1-style method-on-cache shape.
- JSON snapshot round-trip for RaceState — `to_json()` exports the full cache (source / freshness / last_update_ms / track_name / ver / export_id / session / track / cars / messages / laps / qualifying / stats_leading/best_laps/best_sectors) with an embedded schema_version tag; `from_json()` / `import_json()` reconstruct / replace, preserving the idempotency contract across the round-trip.
- Transport Protocol (runtime_checkable), 8-class NLSError hierarchy, ReplayTransport with D-07 backward-compat + speed_factor, and async-isolated JsonlRecorder — all 12 transport-related requirements delivered with 210 passing tests
- WebSocket-based live Transport with multiplexed handshake, app-level keepalive from `{type:"time"}` frames, jittered exponential reconnect on transient close codes, and a stateful LTS_NOT_FOUND three-state classifier with per-reason policy
- RecordingTransport composition wrapper (append-then-yield invariant, Transport-Protocol symmetric), `fetch_laps_data` HTTP fallback with HA-friendly `httpx.AsyncClient` injection + HTML/JSON/non-object detection, and end-to-end integration tests proving the recorder↔replay round-trip invariant
- One-liner:
- NLSClient composition root wires Transport -> RaceState with three async iterators and cancellation-safe lifecycle; exception hierarchy finalized with LTSNotFoundError and ParseError (D-23/D-24) and re-purposed UnknownEventError for --strict mode.
- Shipped two console scripts (`nls-record` + `nls-replay`) per D-01..D-05, hard-cutting the Phase 1 `aionlslivetiming-capture` tool; nls-replay supports --speed/--limit/--show-time-sync/--strict/--summary with strict-mode exit-1 semantics per D-25.
- Three runnable Python examples (live + replay + filter walkthrough) backed by a 7-line bundled JSONL fixture, with mocked-transport tests covering all three — no live server required.
- Complete documentation set: slim PyPI landing surface (README + LICENSE + CHANGELOG + CONTRIBUTING) plus mkdocs-material site with auto-generated API reference and 3 mirrored worked examples — 16 completeness tests gate the bar
- 1. [Rule 1 - Bug] Fixed `uv build --outdir` wrong flag in tests

---
