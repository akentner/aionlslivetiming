# Roadmap: AIO NLS Livetiming API

## Overview

Build a bottom-up async-first Python client library for the Nürburgring Langstrecken-Serie livetiming WebSocket feed. The library exposes typed Python objects and a queryable cache with one shared API surface for live and replayed-from-JSONL data. We start with the pure-function parser and package skeleton (zero I/O, fastest tests), add the idempotent state and filter DSL, then wire up the live WebSocket transport, replay transport, recording wrapper, and HTTP fallback, and finish with the composition-root client, CLI entry points, and PyPI-ready distribution.

## Phases

- [ ] **Phase 1: Foundation (Package + Parser)** - Skeleton, HA-pinned deps, 8 typed Message dataclasses, per-PID parsers, UnknownMessage fallback, parser fixtures and unit tests
- [ ] **Phase 2: State + Filtering** - Idempotent RaceState, filter DSL (class/starting_no/driver/position/lap/sector), cache freshness, JSON export/import
- [ ] **Phase 3: Transport + Replay** - Transport Protocol, LiveTransport (WebSocket + reconnect + heartbeat), ReplayTransport, RecordingTransport wrapper, HTTP laps-data fallback
- [ ] **Phase 4: Client + Distribution** - NLSClient composition root, async stream API with cancellation safety, CLI entry points, README/API ref/CHANGELOG/LICENSE/CONTRIBUTING, PyPI publish prep

## Phase Details

### Phase 1: Foundation (Package + Parser)
**Goal**: A working, unit-testable parser that decodes all known short-code server payloads into typed Message objects, plus a packaged src-layout project with HA-pinned dependencies and `py.typed`.
**Depends on**: Nothing (first phase)
**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05, DIST-02, DIST-03, DIST-06, DIST-07
**Success Criteria** (what must be TRUE):
  1. User can `uv sync --extra dev` (per README.md canonical install command) on Python 3.12+ and run `uv run pytest` with parser tests passing against fixture JSONs — no live server or network required
  2. Calling `parse(raw_dict)` on any known short-code payload returns the corresponding typed Message dataclass (`InitialStateMessage`, `TrackStateMessage`, `RaceMessage`, `PerCarLapsMessage`, `QualifyingMessage`, `StatisticsMessage`, `TimeSyncMessage`, or `UnknownMessage`)
  3. Each Message is a frozen dataclass with explicit fields and a `.raw` attribute preserving the original server payload so unknown fields never cause a crash
  4. Unknown PIDs produce an `UnknownMessage` with the raw payload attached, logged at WARNING — the library never raises on unrecognized server schema
  5. Time-sync frames (`{type: "time", value: <ms>}`) are dispatched separately from race messages and never enter the race-message stream
  6. Package ships `py.typed` (PEP 561), pins HA-compatible dependency versions (pydantic, httpx, websockets), and parser/state layers reach ≥80% test coverage
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Package skeleton (hatchling, src layout, py.typed, HA-pinned deps) + D-07 JSONL logger CLI
- [x] 01-02-PLAN.md — 8 frozen Message dataclasses + 10 hand-crafted fixture JSONs (D-08) + dataclass unit tests
- [x] 01-03-PLAN.md — 8 per-PID parsers + `parse()` dispatcher (match/case) + per-PID unit tests + log-dedupe + ≥80% coverage gate

### Phase 2: State + Filtering
**Goal**: A queryable `RaceState` cache with idempotent message application, composable filters across six dimensions, freshness tracking, and JSON snapshot round-trip.
**Depends on**: Phase 1
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04, STATE-05, STATE-06, STATE-07, FILT-01, FILT-02, FILT-03, FILT-04, FILT-05, FILT-06, FILT-07
**Success Criteria** (what must be TRUE):
  1. User can apply any typed Message to `state.apply(msg)` and observe updated standings, per-car lap history, sector times, race messages, qualifying, and statistics through synchronous query methods
  2. Applying the same message to `RaceState` twice produces identical state — idempotency is the public contract (verifiable without network)
  3. User can filter cached cars by class, starting number (single or list), driver name, position range, lap range, and sector-time threshold, and compose multiple filters with AND semantics
  4. `state.freshness` reports `FRESH` / `STALE` / `RESYNCING` and `source` reports `LIVE` / `REPLAY` / `IMPORTED`, and `state.clear()` resets all sub-caches
  5. User can export the state to JSON and re-import the same JSON to obtain a structurally equivalent state
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — state module skeleton + Source/Freshness enums + pydantic state models + idempotent RaceState.apply() + freshness/source/clear()
- [ ] 02-02-PLAN.md — composable Filter DSL (class/starting_no/driver/position/lap/sector_time_lt) + AND composition + RaceState.filter() factory + convenience pass-throughs
- [ ] 02-03-PLAN.md — JSON snapshot persistence (to_json / from_json / import_json) with schema_version tag + round-trip + idempotency-key preservation

### Phase 3: Transport + Replay
**Goal**: A transport interface with three implementations (live WebSocket, JSONL replay, recording wrapper) plus the optional HTTP laps-data fallback — all feeding the same parser path so live and replay produce identical typed Messages.
**Depends on**: Phase 2
**Requirements**: CONN-01, CONN-02, CONN-03, CONN-04, CONN-05, CONN-06, CONN-07, CONN-08, STREAM-01, STREAM-02, STREAM-03, STREAM-04, REC-01, REC-02, REC-03, REC-04, REC-05, REC-06, HTTP-01, HTTP-02, HTTP-03
**Success Criteria** (what must be TRUE):
  1. User can connect to `wss://livetiming.azurewebsites.net/` by event id, send the handshake JSON, and receive typed Messages on a single multiplexed socket
  2. User can subscribe to any combination of channels (0/4 results+track, 3 race messages, 7 per-car laps with `{session, startingNo}`, 501 qualifying, 9002 statistics) and cleanly disconnect to release the socket
  3. Client auto-reconnects with jittered exponential backoff on transient errors, honors the server's `{type:"time"}` heartbeat to drive application-level keepalive, surfaces `LTS_NOT_FOUND` as a typed three-state event (not_yet_started / ended / unknown_event), and survives session transitions (qualifying → heat → race) without crashing or losing cached state
  4. User can record a live stream to a JSONL file (one parsed message per line) and replay that file through an identical API surface with optional speed multiplier — fully usable offline
  5. User can fetch the optional `/event/{id}/laps-data` endpoint via an HA-compatible async HTTP client (httpx), with graceful handling when the server returns HTML instead of JSON
**Plans**: TBD

### Phase 4: Client + Distribution
**Goal**: A single `NLSClient` composition root that wires transport → parser → state with cancellation-safe async iteration, plus CLI entry points, complete documentation, and a publish-ready PyPI package.
**Depends on**: Phase 3
**Requirements**: DIST-01, DIST-04, DIST-05, DOC-01, DOC-02, DOC-03, DOC-04, DOC-05
**Success Criteria** (what must be TRUE):
  1. User can drive both live and replay through `async with NLSClient(...) as client: async for msg in client.messages(): ...` and obtain typed Message objects with clean cancellation (no leaked tasks, WS closed within 1s)
  2. The `aionlslivetiming` package has zero `homeassistant.*` imports — it installs and runs as a generic Python package
  3. User can invoke `python -m aionlslivetiming record <event_id> <file>` and `python -m aionlslivetiming replay <file>` from the command line without writing any Python
  4. The package is publish-ready to PyPI as `aionlslivetiming` with `py.typed`, MIT LICENSE, README (install + quickstart covering live + replay + recording + filter examples), CHANGELOG from v0.1.0, CONTRIBUTING guide, an API reference (mkdocs or pdoc), and at least 3 worked examples
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation (Package + Parser) | 4/4 | Complete | 2026-06-20 |
| 2. State + Filtering | 0/3 | Planned | - |
| 3. Transport + Replay | 0/TBD | Not started | - |
| 4. Client + Distribution | 0/TBD | Not started | - |
