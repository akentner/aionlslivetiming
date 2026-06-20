# Phase 3: Transport + Replay - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning

<domain>
## Phase Boundary

A transport interface with three implementations plus the optional HTTP laps-data fallback — all feeding the same `parse()` path so live and replay produce identical typed `Message` objects.

**In scope:**

1. **`Transport` `typing.Protocol`** in `transport/base.py` — the single interface live, replay, and recording all implement. Methods: `async connect()`, `async close()`, async iteration yielding `Message`.
2. **`LiveTransport`** in `transport/websocket.py` — opens `wss://livetiming.azurewebsites.net/`, sends the `{eventId, eventPid, clientLocalTime}` handshake, drives app-level keepalive from the server's `{type:"time"}` frames, dispatches raw frames to `parser.parse()`, classifies close codes, runs jittered exponential backoff on transient errors, surfaces `LTS_NOT_FOUND` as a typed three-state event.
3. **`ReplayTransport`** in `transport/replay.py` — reads a JSONL log line-by-line, validates header / ordering / partial trailing lines, runs each `raw` through `parser.parse()`, optional `speed_factor` and `suppress_time_sync` knobs.
4. **`RecordingTransport`** wrapper in `transport/recorder.py` — composes any inner `Transport` and tees every yielded message to a `JsonlRecorder`. Async-isolated writer task. No subclassing.
5. **`JsonlRecorder`** in `recorder/jsonl.py` — append-only file with the Phase 3 schema `{ts_recv_ms, event_pid, raw, parsed}` (strict superset of Phase 1's D-07 `{ts_recv_ms, raw}`). Round-trips with `ReplayTransport`.
6. **HTTP laps-data fallback** in `http/laps_data.py` — best-effort `httpx`-based fetch of `/event/{id}/laps-data?session=...&startingNo=...`, graceful degradation (server returns HTML, not JSON) with a typed exception.
7. **Exception hierarchy** in `exceptions.py` — `NLSError` base, plus the concrete types required by CONN/REC/HTTP requirements.

**Explicitly out of scope** (Phase 4):

- `NLSClient` composition root, `client.messages()` async-iterator composition
- `async with` lifecycle on the top-level client (the transport lifecycle is its own)
- CLI entry points (`nls-record` / `nls-replay`) — currently `cli/jsonl_logger.py` from D-07 is a separate Phase 1 tool that will be replaced/aliased
- README/API reference/CHANGELOG/LICENSE/PyPI publish
- Any `homeassistant.*` imports

</domain>

<decisions>
## Implementation Decisions

### Heartbeat & keepalive (CONN-04, CONN-03)

- **D-01:** `websockets.connect(..., ping_interval=None, ping_timeout=None, close_timeout=5)` — the library drives heartbeats itself rather than letting `websockets` ping. Library default `close_timeout=5` (low to avoid hanging on Azure silent close).
- **D-02:** `LiveTransport` runs an app-level keepalive loop: track wall-clock of last received frame (any frame, including time-sync). If no frame for `idle_timeout_s` (default **90 s**), the transport closes the underlying socket and lets the reconnect loop take over. 90 s is comfortably under Azure ARR's ~4 min idle timeout and well above any reasonable per-frame interval during a race.
- **D-03:** Close-code policy (locks which codes trigger reconnect): reconnect on `1006` (abnormal — the actual Azure silent close), `1011` (server error), `1012` (server restart), `1013` (try later). Do **not** reconnect on `1000` (normal closure) or `1001` (going away). `1005` (no status received) is treated as `1006`.
- **D-04:** Time-sync messages (`{type:"time", value:<ms>}`) update the library's `clock_offset` helper (server time minus local time at recv) and are yielded on a **dedicated** `time_sync()` async iterator on `LiveTransport`. They never enter `messages()`. This matches the parser dispatcher's D-05 invariant.

### `LTS_NOT_FOUND` policy (CONN-05, Pitfall #5)

- **D-05:** `LTS_NOT_FOUND` from PID 0 yields a typed event `LTSNotFoundEvent(reason: Literal["not_yet_started", "ended", "unknown_event"])` on a dedicated `lts_not_found()` async iterator on `LiveTransport`. The three states are documented in the type alias and in `LTSNotFoundReason`.
- **D-06:** Classification is a best-guess heuristic from transport state (configurable thresholds):
  - `not_yet_started` — connection is < `pre_race_threshold_s` (default 300 s = 5 min) old AND no `InitialStateMessage` with a non-empty `RESULT` has been seen yet.
  - `ended` — a previous `TrackStateMessage` had `TRACKSTATE` in `{FINISHED, CHEQUERED}` or carried a non-empty `ENDTIME`.
  - `unknown_event` — fallthrough. Default.
- **D-07:** Per-reason default behavior (configurable via `LTSNotFoundPolicy` constructor parameter on `LiveTransport`):
  - `not_yet_started` → silent reconnect (continue the backoff loop; eventually the session starts).
  - `ended` → terminal: stop reconnecting, mark the connection `ended`, allow the cached `RaceState` to remain queryable for replay-style inspection. Yield a final `LTSNotFoundEvent` and close cleanly.
  - `unknown_event` → raise `UnknownEventError` (a `NLSError` subclass). Consumer's responsibility to handle.
- **D-08:** `LTSNotFoundPolicy` is a small dataclass / enum-like class with the three reasons as fields; default is `LTSNotFoundPolicy()` (sensible defaults from D-07). Consumers can override per-reason behavior. Example: an analytics consumer might set `on_ended="continue"` (still consume the cached state without terminating).

### Reconnect backoff (CONN-03, Pitfall #6)

- **D-09:** `ReconnectPolicy(base_delay_s: float = 1.0, cap_delay_s: float = 60.0, max_attempts: int | None = None, initial_offset_s: float = 10.0, honor_retry_after: bool = True)` — constructor parameter on `LiveTransport`.
- **D-10:** Delay formula: `delay = random.uniform(0, min(cap_delay_s, base_delay_s * (2 ** attempt)))` with `attempt` starting at 0 and incrementing per failed reconnect. Full jitter (not decorrelated jitter). `max_attempts=None` means infinite (sensible default — Azure outages can last hours; consumer can wrap `connect()` in a timeout if they want).
- **D-11:** Per-process random initial offset: before the **first** attempt, sleep `random.uniform(0, initial_offset_s)`. Resets after each successful connection that runs for > 60 s (so a reconnect after a 4-hour race is not delayed by an extra offset). This breaks the synchronized reconnect-storm pattern across many concurrent consumers.
- **D-12:** Honor `Retry-After`: if the close frame carries a `Retry-After` header (rare but possible), use `max(delay, retry_after)` for the next backoff. Respect `honor_retry_after=False` to disable.
- **D-13:** `LTSNotFoundEvent(reason="not_yet_started")` reuses the same backoff loop — it's just another transient failure for the purposes of `attempt` counting, but never counts toward `max_attempts` (those apply to network-level failures only).

### Replay speed & time semantics (REC-05, Pitfall #10)

- **D-14:** `ReplayTransport(path: str | Path, *, speed_factor: float = 1.0, suppress_time_sync: bool = True)` — both knobs are constructor params with safe defaults.
- **D-15:** `speed_factor=1.0` → real-time replay using `asyncio.sleep(delta)` between successive `ts_recv_ms` values. `speed_factor=0` → burst mode (no sleeps; replay as fast as the disk + parser allow). `speed_factor>1` → faster than real-time (e.g. `10.0` = ten times faster). Negative values rejected at construction time (`ValueError`).
- **D-16:** Time-sync messages in replay are **informational**: they update the same `clock_offset` helper as live mode but are **not** yielded to `messages()` unless `suppress_time_sync=False`. Default `True` to keep replay/live parity tight (a consumer iterating `messages()` in replay sees the same kinds of messages as in live). When `suppress_time_sync=False`, yield them as `TimeSyncMessage` instances on `messages()` — identical to live behavior, no special path.
- **D-17:** JSONL replay validation:
  - Empty file → raise `ReplayEmptyError`.
  - Line missing `raw` field → raise `ReplaySchemaError(line_no=...)`.
  - `ts_recv_ms` not monotonically non-decreasing → raise `ReplayOrderingError(line_no=..., prev=..., curr=...)`. Strict ordering preserves the cache's ordering invariant (Pitfall #10).
  - Trailing line without newline, or line with invalid JSON → log `WARNING` once with line number, skip, continue. Matches the "looks done but isn't" checklist.

### the agent's Discretion

- Internal file layout under `src/aionlslivetiming/transport/` — `base.py` (Protocol + result types), `websocket.py`, `replay.py`, `recorder.py`. ARCHITECTURE.md lines 57-62 is the default; planner may consolidate `recorder/jsonl.py` into `transport/recorder.py` if a single file is cleaner.
- `JsonlRecorder` API shape (`append(msg)` async vs. push to queue) — async-isolated writer task via `asyncio.Queue` is the recommended pattern from Pitfall #7 / PITFALLS.md but planner can pick the exact API.
- Exact `__repr__` of `LTSNotFoundEvent`, `LTSNotFoundReason`, `ReconnectPolicy`.
- Internal field names on `LTSNotFoundPolicy` (e.g., `on_not_yet_started` vs. `not_yet_started_handler` — call-site readability is the only constraint).
- Whether `LiveTransport.connect()` returns `self` (allowing `await LiveTransport(...).connect()` chaining) or returns `None`. Default to `None` to match `websockets.connect`, but the planner may choose ergonomics.
- Exact `NLSError` exception hierarchy shape (see "Deferred" — discussed but not yet locked, see D-EXC in deferred section).
- HTTP fallback: separate `httpx.AsyncClient` per call vs. accept an injected client (matches HA's `create_async_httpx_client` pattern from STACK.md). Planner decides; injected client is the HA-friendly default.

### Folded Todos

None — `gsd-tools todo match-phase 3` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & requirements

- `.planning/PROJECT.md` — vision, requirements, reverse-engineering notes (server schema, channel IDs, handshake shape, `/laps-data` HTML behavior, Azure hosting context)
- `.planning/REQUIREMENTS.md` — CONN-01..08, STREAM-01..04, REC-01..06, HTTP-01..03 (Phase 3 scope) and full v1 set for downstream awareness
- `.planning/ROADMAP.md` §Phase 3 — success criteria, requirement mapping (CONN+STREAM+REC+HTTP = 21 requirements)
- `.planning/STATE.md` — accumulated decisions from Phases 1–2 (JsonlLogger CLI exists at `src/aionlslivetiming/cli/jsonl_logger.py`; `Source`/`Freshness` enums already on `RaceState`)

### Stack & architecture (locked)

- `.planning/research/STACK.md` — exact dependency versions, HA pin rationale, library comparison (`websockets`, `pydantic`, `httpx` choice)
- `.planning/research/ARCHITECTURE.md` — 5-layer pipeline, package layout, Transport Protocol shape (lines 248–262), recording wrapper pattern (lines 264–299), cache convergence semantics (lines 222–234), testability gradient (lines 477–488)
- `.planning/research/SUMMARY.md` §Architecture Approach, §Pitfalls — exec summary the planner can read instead of long-form docs
- `.planning/research/PITFALLS.md` — pitfall #1 (Azure idle timeout), #5 (LTS_NOT_FOUND), #6 (reconnect storms), #7 (blocking I/O), #8 (cancellation safety), #10 (replay parity), #11 (stale cache), #12 (file rotation)

### Prior phase context

- `.planning/phases/01-foundation-package-parser/01-CONTEXT.md` — D-05 (time-sync dispatcher order), D-07 (JSONL line shape subset), D-10 (HA-pinned deps), D-12 (pytest-asyncio auto mode)
- `.planning/phases/02-state-filtering/` — `Source` enum (`LIVE`/`REPLAY`/`IMPORTED`) and `Freshness` enum (`FRESH`/`STALE`/`RESYNCING`) are exported from `aionlslivetiming.state` and re-exported at the package root; idempotent `apply()` contract

### Server protocol (reverse-engineering notes)

- `.planning/PROJECT.md` §Context — host `wss://livetiming.azurewebsites.net/`, channel PIDs 0/3/4/7/501/9002, payload keys (PID/VER/EXPORTID/SESSION/CUP/HEAT/HEATTYPE/TRACKNAME/STQ/BEST/TOD/RESULT/TRACKSTATE/TIMESTATE/ENDTIME/LTS_NOT_FOUND), handshake shape `{eventId, eventPid, clientLocalTime}`, `{type:"time"}` time-sync prelude
- `src/aionlslivetiming/cli/jsonl_logger.py` — Phase 1's D-07 JSONL tee CLI; reference for handshake format, default channel list, channel ID constants. Its line shape `{ts_recv_ms, raw}` is the strict subset of the Phase 3 recorder schema `{ts_recv_ms, event_pid, raw, parsed}`
- `src/aionlslivetiming/parser/channels.py` — `EVENT_PID_RESULT/RACE_MESSAGE/TRACK_STATE/PER_CAR_LAPS/QUALIFYING/STATISTICS` integer constants
- `src/aionlslivetiming/parser/__init__.py` — the single `parse(raw)` dispatcher; transport modules MUST call this for every non-time-sync frame
- `src/aionlslivetiming/state/__init__.py` and `.planning/research/ARCHITECTURE.md` §Public API Surface — what state types are exposed; `Source` enum already exists

### External (HA core, for dep version verification only — no HA imports)

- `https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/package_constraints.txt` — authoritative source for `pydantic==2.13.4`, `httpx==0.28.1`, `websockets>=15.0.1`, `orjson==3.11.9`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`src/aionlslivetiming/cli/jsonl_logger.py`** — D-07 JSONL tee CLI; connects to the production WS, sends handshake, dumps raw frames. Provides the **default channel list** `(0, 3, 4, 7, 501, 9002)` and the **default host** `wss://livetiming.azurewebsites.net/`. Phase 3's `LiveTransport` should reuse these constants rather than redefine them. Extract to `transport/_defaults.py` or similar.
- **`src/aionlslivetiming/parser/channels.py`** — `EVENT_PID_*` integer constants for the 6 channels. Use these instead of magic numbers throughout Phase 3.
- **`src/aionlslivetiming/parser/__init__.py::parse(raw)`** — the single `parse()` dispatcher. Every transport must call this for every non-time-sync frame (no per-transport shortcut parsers). Already includes the `PID == 0` fallback for `LTS_NOT_FOUND` frames that omit `eventPid`.
- **`src/aionlslivetiming/state/`** — `Source` enum (`LIVE`/`REPLAY`/`IMPORTED`), `Freshness` enum (`FRESH`/`STALE`/`RESYNCING`), idempotent `RaceState.apply()`. Already-locked Phase 2 decisions apply. Transports should **not** import or mutate `RaceState` directly (ARCHITECTURE.md boundary rule #3) — only the Phase 4 client does.

### Established Patterns

- **One-file-per-PID in `parser/`** — `LiveTransport`'s raw-frame handling should mirror this by routing every frame through the single `parse(raw)` chokepoint, not branching on PID locally.
- **Frozen dataclasses with `.raw` field** — every `Message` variant carries `.raw: Mapping[str, Any]` (forward-compat). Recording can serialize `.raw` directly without losing schema-drift fields.
- **Stdlib `logging.getLogger("aionlslivetiming.transport")`** — sub-logger for the transport package; HA-friendly (no separate logger setup required).
- **`websockets_factory: Callable | None` injection pattern** — `jsonl_logger.py` already uses this for testability. Reuse in `LiveTransport` so CI smoke tests can pass a mock factory.
- **`orjson` with stdlib `json` fallback** — D-10 fallback pattern already exists in `jsonl_logger.py::run()`. Reuse in `JsonlRecorder` and `ReplayTransport`.

### Integration Points

- `parser.parse(raw)` is the single entry point. `LiveTransport._reader_task` (or similar) calls `parse(payload)` for every frame after the `{type:"time"}` branch.
- The Phase 1 `cli/jsonl_logger.py` produces JSONL with `{ts_recv_ms, raw}` only. `ReplayTransport` MUST accept this line shape (treat missing `event_pid` and `parsed` as absent — fall back to `raw.get("eventPid")` and skip `parsed`). Phase 3's `JsonlRecorder` writes the richer `{ts_recv_ms, event_pid, raw, parsed}` shape (strict superset), so a D-07 JSONL is always replayable, and a Phase 3 JSONL is the new public contract going forward.
- `RaceState.Source` enum (`LIVE`/`REPLAY`/`IMPORTED`) is the bridge between transport and state. `LiveTransport` is the only transport that produces `Source.LIVE`; `ReplayTransport` is the only one that produces `Source.REPLAY`. The Phase 4 client decides where this is set (likely on the client, not the transport — keeps transports stateless).

</code_context>

<specifics>
## Specific Ideas

- The **time-sync-as-informational** pattern (D-04, D-16) is the same invariant in live and replay — keep them identical so `client.messages()` is truly source-agnostic. A consumer iterating `messages()` in either mode should never see a `TimeSyncMessage` unless they opt in (`suppress_time_sync=False` on replay, or subscribe to `time_sync()` on live).
- The **three-state `LTS_NOT_FOUND`** classification (D-05, D-06) relies on observing `TrackStateMessage` over time. The classifier must be **stateful** across the transport's lifetime (it remembers whether a FINISHED/CHEQUERED state was seen). This is the only stateful transport piece besides the reconnect attempt counter — keep it as a small private helper, not a full object.
- The **strict ordering invariant** (D-17) protects the cache: a non-monotonic JSONL means the recorder upstream had a bug (concurrent writes, clock skew, manual edit). Raising `ReplayOrderingError` is loud, not silent. Document this in the `JsonlRecorder` docstring as "if you ever see this, your recording infrastructure has a bug — file an issue".
- `RecordingTransport` is **composition, not subclass** (ARCHITECTURE.md pattern 2, REC-03). `LiveTransport(RecordingTransport(inner=LiveTransport(...), rec=JsonlRecorder(path)))` is a valid construction — the wrapper composes symmetrically. Don't make it `LiveTransport` subclass `RecordingTransport` or vice versa.
- The `idle_timeout_s=90` default (D-02) is conservative — Azure ARR's documented idle timeout is ~4 min, and 90 s is ~2.5× safety margin. But during pre-race hours the server may legitimately be silent for minutes. Configurable so analytics consumers can crank it up; live-display consumers can leave it at default.
- The `ReconnectPolicy.initial_offset_s=10` default (D-11) means a process that just started has up to a 10 s head-start delay before its first connect attempt. This is the cheapest defense against reconnect storms — most consumers will never notice the 10 s delay.

</specifics>

<deferred>
## Deferred Ideas

### Reviewed Todos (not folded)

None — no todos matched Phase 3 scope.

### From discussion

- **D-EXC (exception hierarchy)** — discussed but not yet locked. Out of scope for Phase 3 in the sense that the discussion was not deep-dived. Plausible shape: `NLSError(Exception)` base; `ConnectionError`, `ParseError`, `SchemaError`, `UnknownEventError`, `LTSNotFoundError` (or split per-reason), `ReplayError` (with `ReplayEmptyError`, `ReplayOrderingError`, `ReplaySchemaError` subclasses), `NLSHttpFallbackUnavailable`. **Resolve at Phase 4's discuss-phase** since the public exception names are part of the published API surface that the CLI / client exposes. For now, the planner should pick a minimal set that satisfies Phase 3's requirements (at minimum `NLSError`, `ConnectionError`, `UnknownEventError`, `ReplayError` / its subclasses, `NLSHttpFallbackUnavailable`) and document the names as "preliminary, may move to `aionlslivetiming.exceptions`" in the Phase 3 plan.
- **HTTP laps-data fallback behavior** — out of scope for this discuss-phase. PROJECT.md already documents that the server returns HTML; planner should default to `NLSHttpFallbackUnavailable` raised with a "use channel 7 instead" message when the server returns non-JSON or HTML. If the user later wants scraping, that's a separate phase.

### Out of scope for this phase

- CLI entry points (`nls-record` / `nls-replay`) — Phase 4. The Phase 1 `cli/jsonl_logger.py` remains in place until replaced.
- `NLSClient` composition root, `client.messages()` async-iterator, `async with` lifecycle — Phase 4.
- File rotation (Pitfall #12, 100 MB / hourly) — not in Phase 3 scope per ROADMAP.md. The `JsonlRecorder` writes a single file; rotation belongs in a future phase if real-world recording hits the disk-size limit.
- `clock_offset` API surface — implied by D-04 / D-16 but the exact public method shape (`transport.clock_offset`, `transport.time_offset_ms()`, or `time_sync_callback` registration) is not locked. Planner should pick the simplest synchronous helper (e.g., `transport.clock_offset_ms: float | None` property) and move on.

</deferred>

---

*Phase: 03-transport-replay*
*Context gathered: 2026-06-21*
