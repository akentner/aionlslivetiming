# Requirements: AIO NLS Livetiming API

**Defined:** 2026-06-20
**Core Value:** Downstream Python projects can subscribe to a running NLS race and get typed, filtered, cached race data — live or replayed from a log — without ever touching the Azure WebSocket or the cryptic short-code JSON the server actually emits.

## v1 Requirements

### Connection

- [ ] **CONN-01**: User can connect to the livetiming WebSocket at `wss://livetiming.azurewebsites.net/` by event id
- [ ] **CONN-02**: User can disconnect cleanly and release the underlying socket
- [ ] **CONN-03**: Client auto-reconnects on transient network errors with jittered exponential backoff
- [ ] **CONN-04**: Client honors the server's time-sync message (`{type: "time", value: <ms>}`) and exposes a clock-offset helper
- [ ] **CONN-05**: Client surfaces `LTS_NOT_FOUND` as a typed event, not an exception, by default
- [ ] **CONN-06**: Client can subscribe to any combination of channels (0/4, 3, 7, 501, 9002) and the per-car laps channel accepts `{ session, startingNo }`
- [ ] **CONN-07**: Client survives race session transitions (qualifying → heat → race) without crashing or losing cached state
- [ ] **CONN-08**: User can override the base host for testing or local development

### Parsing

- [x] **PARSE-01**: Library decodes all known short-code JSON keys (`PID`, `VER`, `EXPORTID`, `SESSION`, `CUP`, `HEAT`, `HEATTYPE`, `TRACKNAME`, `STQ`, `BEST`, `TOD`, `RESULT`, `TRACKSTATE`, `TIMESTATE`, `ENDTIME`, `LTS_NOT_FOUND`) into typed Python objects
- [x] **PARSE-02**: Library exposes 8 typed message classes (InitialState, TrackStateUpdate, RaceMessage, PerCarLaps, Qualifying, Statistics, TimeSync, UnknownMessage)
- [x] **PARSE-03**: Unknown or new server fields are preserved on the message's `.raw` attribute and never cause a crash
- [x] **PARSE-04**: Parser is pure (no I/O, no event-loop dependency) so it is unit-testable with fixture JSONs
- [x] **PARSE-05**: Each typed message is a frozen dataclass / pydantic model with explicit fields

### Cached State

- [x] **STATE-01**: Library maintains a queryable `RaceState` (current standings, per-car lap history, sector times, race messages, qualifying, statistics)
- [x] **STATE-02**: State is updated by a single-writer task (the message reader) and read by many consumers — no locks
- [x] **STATE-03**: `RaceState.apply(message)` is idempotent: applying the same message twice produces the same state
- [x] **STATE-04**: State exposes a `freshness` indicator (time of last update, source = live/replay/imported)
- [x] **STATE-05**: User can clear the cache on demand (resets all sub-caches)
- [ ] **STATE-06**: User can export the state to JSON
- [ ] **STATE-07**: User can import a state from JSON (replaces current state)

### Filtering

- [x] **FILT-01**: User can filter cars by class (car class name)
- [x] **FILT-02**: User can filter by starting number (single value or list)
- [x] **FILT-03**: User can filter by driver name
- [x] **FILT-04**: User can filter by position range (e.g., top 5)
- [x] **FILT-05**: User can filter by lap range (e.g., last 10 laps)
- [x] **FILT-06**: User can filter by sector time threshold (cars faster than X)
- [x] **FILT-07**: Filter API is composable (multiple filters combine with AND)

### Live Event Stream

- [ ] **STREAM-01**: User can iterate `async for msg in client.messages()` to consume every parsed message in order
- [ ] **STREAM-02**: Stream yields typed message objects, never raw dicts
- [ ] **STREAM-03**: Stream handles backpressure gracefully (slow consumer doesn't crash the reader task)
- [ ] **STREAM-04**: User can cancel the stream cleanly without leaving dangling tasks

### Recording & Replay

- [ ] **REC-01**: User can record the live WebSocket message stream to a JSONL file (one parsed message per line)
- [ ] **REC-02**: Recorder can be enabled/disabled at runtime
- [ ] **REC-03**: Recorder is implemented as a transport wrapper, not a subclass — works over any transport
- [ ] **REC-04**: User can replay a JSONL log through the same API surface as a live connection
- [ ] **REC-05**: Replay preserves message order and timing (or has a speed-multiplier option)
- [ ] **REC-06**: Replay is independent of any live network — fully usable offline

### HTTP

- [ ] **HTTP-01**: Library can fetch the per-car laps HTML page from `/event/{id}/laps-data?session=...&startingNo=...`
- [ ] **HTTP-02**: HTTP fetch uses HA-compatible async HTTP client (httpx)
- [ ] **HTTP-03**: HTTP endpoint is best-effort; library does not crash if the server returns HTML instead of JSON

### Distribution & Ergonomics

- [ ] **DIST-01**: Library is published to PyPI as `aionlslivetiming`
- [x] **DIST-02**: Library uses `py.typed` (PEP 561) and ships type hints
- [x] **DIST-03**: Library targets Python 3.12+ and documents that in the README
- [ ] **DIST-04**: Library has zero HA-specific imports — usable as a generic Python package
- [ ] **DIST-05**: Library provides a CLI entry point for `nls-record` and `nls-replay`
- [x] **DIST-06**: Library has ≥80% test coverage for the parser, state, and filter layers
- [x] **DIST-07**: Library uses HA-pinned dependency versions (pydantic, httpx, websockets, orjson) to avoid version float

### Documentation & Community

- [ ] **DOC-01**: README with install, quickstart (live + replay), filter examples, and recording example
- [ ] **DOC-02**: API reference published (mkdocs or pdoc)
- [ ] **DOC-03**: CHANGELOG.md maintained from v0.1.0
- [ ] **DOC-04**: MIT LICENSE
- [ ] **DOC-05**: CONTRIBUTING.md and at least 3 worked examples

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Filtering

- **FILT-08**: Filter by pit-stop count
- **FILT-09**: Filter by gap to leader / gap to car ahead
- **FILT-10**: Filter by stint age (since last pit)

### Persistence

- **PERS-01**: Optional SQLite-backed state for cross-restart persistence
- **PERS-02**: Optional Parquet/Arrow export for analytics

### Statistics

- **STAT-01**: Aggregate per-driver fastest laps across multiple sessions
- **STAT-02**: Season standings computation
- **STAT-03**: Lap-time distribution histograms

### HA Integration

- **HAI-01**: A separate `aionlslivetiming-ha` custom_component wrapping this library
- **HAI-02**: Sensor entities for current position, last lap, gap, best lap
- **HAI-03**: Config flow for selecting event + which teams to track

### Multi-Source

- **MULT-01**: Combine live + replay sources (e.g., resume replay from a recorded point, then switch to live)
- **MULT-02**: Support for additional livetiming sources that follow the same protocol shape

## Out of Scope

| Feature | Reason |
|---------|--------|
| Submitting to `home-assistant/core` | Lower-friction release; community can adopt via HACS instead |
| Web UI / dashboard | Library only — frontend is a separate concern |
| Pandas / DataFrame as primary type | Forces the dep on every consumer; not needed for async-first use case |
| Persistent database | Files (JSONL/JSON) are sufficient for v1 |
| Authentication against logged-in NLS endpoints | The livetiming service is currently public |
| ML / prediction | Only consume what the server publishes |
| Web scraping the public NLS website | The library targets the WebSocket + the documented REST endpoint only |
| Plotting / visualization | Library only — separate visualization projects can use the data |
| Telemetry (per-second car telemetry, tire data) | Not published by the NLS livetiming service |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONN-01 | Phase 3 | Pending |
| CONN-02 | Phase 3 | Pending |
| CONN-03 | Phase 3 | Pending |
| CONN-04 | Phase 3 | Pending |
| CONN-05 | Phase 3 | Pending |
| CONN-06 | Phase 3 | Pending |
| CONN-07 | Phase 3 | Pending |
| CONN-08 | Phase 3 | Pending |
| PARSE-01 | Phase 1 | Complete |
| PARSE-02 | Phase 1 | Complete |
| PARSE-03 | Phase 1 | Complete |
| PARSE-04 | Phase 1 | Complete |
| PARSE-05 | Phase 1 | Complete |
| STATE-01 | Phase 2 | Complete |
| STATE-02 | Phase 2 | Complete |
| STATE-03 | Phase 2 | Complete |
| STATE-04 | Phase 2 | Complete |
| STATE-05 | Phase 2 | Complete |
| STATE-06 | Phase 2 | Pending |
| STATE-07 | Phase 2 | Pending |
| FILT-01 | Phase 2 | Complete |
| FILT-02 | Phase 2 | Complete |
| FILT-03 | Phase 2 | Complete |
| FILT-04 | Phase 2 | Complete |
| FILT-05 | Phase 2 | Complete |
| FILT-06 | Phase 2 | Complete |
| FILT-07 | Phase 2 | Complete |
| STREAM-01 | Phase 3 | Pending |
| STREAM-02 | Phase 3 | Pending |
| STREAM-03 | Phase 3 | Pending |
| STREAM-04 | Phase 3 | Pending |
| REC-01 | Phase 3 | Pending |
| REC-02 | Phase 3 | Pending |
| REC-03 | Phase 3 | Pending |
| REC-04 | Phase 3 | Pending |
| REC-05 | Phase 3 | Pending |
| REC-06 | Phase 3 | Pending |
| HTTP-01 | Phase 3 | Pending |
| HTTP-02 | Phase 3 | Pending |
| HTTP-03 | Phase 3 | Pending |
| DIST-01 | Phase 4 | Pending |
| DIST-02 | Phase 1 | Complete |
| DIST-03 | Phase 1 | Complete |
| DIST-04 | Phase 4 | Pending |
| DIST-05 | Phase 4 | Pending |
| DIST-06 | Phase 1 | Complete |
| DIST-07 | Phase 1 | Complete |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| DOC-03 | Phase 4 | Pending |
| DOC-04 | Phase 4 | Pending |
| DOC-05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 52 total
- Mapped to phases: 52 ✓
- Unmapped: 0

**Coverage by phase:**
- Phase 1 (Foundation): 9 requirements (PARSE-01..05, DIST-02, DIST-03, DIST-06, DIST-07)
- Phase 2 (State + Filtering): 14 requirements (STATE-01..07, FILT-01..07)
- Phase 3 (Transport + Replay): 21 requirements (CONN-01..08, STREAM-01..04, REC-01..06, HTTP-01..03)
- Phase 4 (Client + Distribution): 8 requirements (DIST-01, DIST-04, DIST-05, DOC-01..05)

---
*Requirements defined: 2026-06-20*
*Last updated: 2026-06-20 after roadmap creation*
