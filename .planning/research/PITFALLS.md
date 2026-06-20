# Pitfalls Research

**Domain:** Async-first Python client library for an undocumented reverse-engineered WebSocket feed (NLS livetiming on Azure App Service)
**Researched:** 2026-06-20
**Confidence:** MEDIUM-HIGH (server-specific items are MEDIUM because the protocol is reverse-engineered and may shift; transport/async/distro items are HIGH because they rest on well-documented Python + Azure behavior)

## Critical Pitfalls

These are domain-specific issues that will surface during the first live race weekend if not addressed in code from day one.

### Pitfall 1: Azure App Service idle timeout closes the WebSocket silently

**What goes wrong:**
Azure App Service has a documented 4-minute idle timeout on WebSocket connections when the frontend hasn't received any data. NLS race feeds are bursty — long quiet stretches between sector updates. The vendor bundle's reconnect wrapper uses a fixed 1-second backoff and retries on close codes 1000/1001/1005, but the *server* initiates close with no payload, and the wrapper treats it as a normal disconnect. Consumers see "session ended" or a flood of reconnects every few minutes during quiet stretches.

**Why it happens:**
The vendor JS was written against IIS/ARR behavior that is more permissive than current Azure App Service defaults. Default `webSockets` are enabled on Azure but idle timeout is enforced at the ARR (Azure Load Balancer) layer, not the application layer, so server-side keepalive on the app's Express server doesn't help.

**How to avoid:**
- Implement an application-level ping/pong heartbeat (every 20-25s) that round-trips the server's existing `{ type: "time", value: <ms> }` mechanism. Use it as a synthetic heartbeat source when no race messages have arrived for N seconds.
- Distinguish "server close" (1000/1001/1005 + expected close frame) from "idle timeout" (close during quiet period). The latter should trigger a reconnect, the former should not.
- Configure `websockets` library with explicit `ping_interval=None` (we drive it ourselves) and `close_timeout` short (<5s).
- On the recorder side, insert a synthetic `_HB` JSONL line every N seconds of quiet so the replay is faithful.

**Warning signs:**
- WebSocket reconnects every 3-5 minutes during a quiet race (no yellow flags, no pit stops)
- Close code 1006 (abnormal closure) repeatedly
- "Session ended" events fired spuriously during qualifying when nothing has actually ended

**Phase to address:**
Transport/connection phase — must be in the initial WebSocket loop, not bolted on later. Affects both live and replay (replay must reproduce the heartbeat semantics for downstream consumers that care about session boundaries).

---

### Pitfall 2: Time-sync messages treated as race data

**What goes wrong:**
The first `onmessage` after `onopen` (and periodically thereafter) is `{ type: "time", value: <ms> }`. This is a server-time heartbeat, not a race payload. If the parser routes it through the same handler as `PID 0/3/4/7/501/9002`, the cache will grow stale `time` fields, replay will replay time-sync messages as if they were race updates, and the `messages()` event stream will be polluted with non-race events.

**Why it happens:**
The short-code JSON schema doesn't include a top-level discriminant the parser can switch on. The `time` message is structurally `{ type, value }` while race messages use `{ PID, ...payload }`. A naïve parser that tries every handler on every message will confuse them.

**How to avoid:**
- Dispatch on the top-level shape before PID lookup: `if "type" == "time"` and `if "PID" in payload` are mutually exclusive and must be the first switch in the dispatcher.
- Surface time-sync messages on a dedicated `time_sync` callback or `AsyncIterator[TimeSync]` — do not mix them with race messages.
- During recording, store time-sync messages with a distinct sentinel (e.g., `__ts__` prefix or a wrapper object) so replay can distinguish them and the recorder can sanity-check them.
- Document the time-sync contract as part of the public API. It is *not* a private implementation detail — downstream HA sensors may want server-time for jitter analysis.

**Warning signs:**
- Cache size grows by 1 on every reconnect during otherwise idle stretches
- Replay fires messages that don't match any known PID and don't look like data
- `messages()` iterator yields messages with a `type` field instead of `pid` field

**Phase to address:**
Parser phase — must be designed in before any caching or replay work begins.

---

### Pitfall 3: Dropped and duplicated messages during high-frequency updates

**What goes wrong:**
The PROJECT.md explicitly calls this out: "the server can drop messages during high-frequency updates". Two failure modes:
- *Drop*: a PID `4` track state update is missed — the next update references laps that the cache doesn't know about. Sector times appear to jump, gap calculations become negative.
- *Duplicate*: a network blip causes the wrapper to resend the last handshake, and the server responds with the same `RESULT` payload twice. Cache gets the same car listed twice unless the consumer deduplicates by `(startingNo, lap)`.

**Why it happens:**
No sequence numbers in the protocol. No client-side ACK. The vendor bundle relies on the next periodic full-state payload to "self-heal" the cache. But the NLS server only sends full state on initial connection, not periodically.

**How to avoid:**
- Design the cache layer to be **idempotent**: applying the same `(startingNo, lap, sector)` tuple twice must be a no-op, not a duplicate.
- Track `last_applied_pid` and `last_applied_ts` per channel. On reconnect, drop stale track state but keep results, qualifying, and statistics (they are session-wide and don't go stale).
- Implement per-channel "skipped messages" counter. If a channel reports >N skipped messages within M seconds, log it as a known issue (matches real server behavior) rather than crashing.
- For per-car laps (channel 7), use the `(session, startingNo)` tuple as the cache key — duplicates collapse automatically.
- Document that consumers must not assume "between two updates, exactly one lap happened". The contract is *eventual convergence*, not *exact ordering*.

**Warning signs:**
- Sector time goes negative
- Lap count for a car decreases
- Cache size grows linearly with message count instead of stabilizing
- Two adjacent messages carry the same `(startingNo, lap, sector)` triple

**Phase to address:**
Cache phase. The idempotency contract must be part of the cache's public API from the start — adding it later is a breaking change.

---

### Pitfall 4: Session transitions (qualifying → heat → race) crash the parser

**What goes wrong:**
`SESSION`, `CUP`, `HEAT`, and `HEATTYPE` can shift mid-connection during a race weekend (Saturday qualifying → Saturday race, then Sunday warmup → Sunday race). The initial handshake binds the connection to one `eventId`, but the server-side *session* changes without notice. If the parser assumes one shape per session type (e.g., qualifying has no pit messages), it crashes when the shape flips.

**Why it happens:**
The short-code schema is not self-describing. Different session types use the same PIDs with different payload shapes. No `SCHEMA_VERSION` field exists.

**How to avoid:**
- Use `dataclasses` (or Pydantic models with `extra="ignore"`) for each known payload shape. Unknown fields are silently dropped, not errors.
- Treat each PID handler as `try/except` around a *partial* model parse — known fields land in typed fields, the rest in a generic `extras: dict` bucket.
- Surface session transitions as a `SessionTransition` event on the public event stream. Don't silently merge state across session boundaries.
- Add a `clear()` method that drops everything in the cache so consumers can reset cleanly on session change.
- Add a circuit breaker: if 3 consecutive messages on the same channel fail to parse, disconnect and reconnect (the server may be in a transitional state and a fresh handshake re-syncs).

**Warning signs:**
- `KeyError` from the parser on a field that worked in the previous race
- Cache reports a car has `laps > total_laps_in_race` after a session transition
- Qualifying results appear in a race session's standings

**Phase to address:**
Parser phase + cache phase. Schema tolerance is a parser concern; cache reset on transition is a cache concern.

---

### Pitfall 5: `LTS_NOT_FOUND` semantics ambiguity

**What goes wrong:**
`LTS_NOT_FOUND` indicates "the session is over or never started" per PROJECT.md. But the server uses it for at least three distinct cases:
1. Session truly ended (chequered flag, session over)
2. Session not yet started (handshake sent too early, before the green flag)
3. Event ID is wrong (typo, off-season, replay of an old event ID)

If the client treats all three the same way, it will:
- Hang forever waiting for data on a session that hasn't started yet (case 2)
- Tear down a perfectly valid connection to a finished session that should be readable for replay (case 1)
- Mask real configuration errors (case 3)

**Why it happens:**
Same short-code shape for all three. Server doesn't include a discriminator or reason.

**How to avoid:**
- Expose `LTS_NOT_FOUND` as an event on the public stream with three distinct states: `not_yet_started`, `ended`, `unknown_event`.
- For `not_yet_started`: implement a backoff retry (every 30s, max 10 minutes) — common pattern for pre-race window.
- For `ended`: stop reconnecting, mark the connection as terminal, allow replay-only mode on the cached state.
- For `unknown_event`: surface as a hard error (`UnknownEventError`) with a clear message. Don't retry.
- Make the distinction configurable: a consumer doing replay/analytics wants `ended` to be a soft state; a consumer doing live display wants `unknown_event` to be a soft state too.

**Warning signs:**
- Consumer reports "the library says the race ended but the race is still running"
- Reconnect loop fires every second after the chequered flag
- Long-running pre-race hangs (consumer waits 10 minutes for a 14:00 race at 13:45)

**Phase to address:**
Parser + transport phases. Both message interpretation and reconnect policy must agree on the semantics.

---

### Pitfall 6: Reconnect storms after an outage

**What goes wrong:**
A network blip or Azure maintenance window closes all open WebSockets at once. Every consumer (HA instance, Discord bot, analytics tool) reconnects simultaneously. The NLS server, hosted on a single Azure App Service instance, can't handle the reconnect wave and serves slow or fails — causing more reconnects. This is a textbook thundering-herd.

**Why it happens:**
The vendor bundle uses fixed 1-second backoff. Every consumer's clock is roughly synchronized. No jitter.

**How to avoid:**
- Exponential backoff with full jitter: `delay = random(0, min(cap, base * 2^attempt))`, cap at ~60s.
- Per-process random initial offset (0-10s) so consumers don't start their backoff clocks simultaneously.
- Honor the server's `Retry-After` if it sends one in a close frame (rare but possible).
- Make the reconnect policy a constructor parameter with sensible defaults — HA consumers may want more aggressive reconnect, analytics tools may want less.
- Document the "wait at least N seconds between reconnects" contract for downstream consumers who write their own reconnect loops.

**Warning signs:**
- Server response time spikes to >5s during the first minute after an outage
- Library's reconnect counter shows synchronized behavior across processes (visible in logs)
- Azure App Service returns 503 during the reconnect wave

**Phase to address:**
Transport phase.

---

### Pitfall 7: Blocking I/O on the event loop

**What goes wrong:**
The hot path receives a WebSocket message, parses JSON, mutates the cache, optionally writes to a JSONL file. The first three are fast. The fourth — file I/O — is not. If `json.dumps(msg, indent=2)` is called on every message during a 4-hour race, the recorder thread (or worse, the event loop itself) blocks on disk. JSONL write is I/O-bound; `json.dumps` is CPU-bound. Both are sync.

Additionally, `aiohttp`/`httpx` for the per-car lap endpoint is fine *if used async*. If a consumer reaches for the sync `requests` library "just for the laps-data call", the event loop stalls.

**Why it happens:**
Python async culture says "use async libs" but it's easy to reach for `json.dumps`, `open()`, `pathlib.Path.write_text()` in the hot path. These are all sync.

**How to avoid:**
- Use `orjson` (faster than `json`, returns `bytes` directly) or `ujson` for serialization. Both are sync but ~5-10x faster than stdlib `json`.
- Run the JSONL recorder on a dedicated `asyncio` task using `asyncio.Queue` between the WS reader and the disk writer. The reader never blocks on disk; the writer never blocks the reader.
- For consumers: clearly mark the recorder as "best-effort" — if disk is slow, messages can be dropped from the log rather than from the cache. Document this.
- Lint rule (or test) that the cache mutators are sync — they must not await, so the event loop can't be blocked by a long cache update.

**Warning signs:**
- `asyncio.get_event_loop().slow_callback_duration` warnings during a race
- Cache updates lag behind WS messages by seconds during heavy disk activity
- Recorder file size grows in bursts (queueing) instead of streaming

**Phase to address:**
Parser phase + recorder phase. Cache must be sync; recorder must be async-isolated.

---

### Pitfall 8: Cancellation safety in the async iterator

**What goes wrong:**
`async for msg in client.messages()` is the public API for consuming the event stream. If the consumer breaks out of the loop (early return, exception), Python's `asyncio` cancellation must reach the WebSocket reader task and the recorder task. If the iterator uses `yield from` patterns or shared state that isn't `finally`-cleaned, the WebSocket stays open, the recorder task leaks, and the next `connect()` call hangs waiting for the previous one.

**Why it happens:**
Async generator cancellation is a 3.7+ feature with subtle semantics. `aclose()` must be called explicitly; `asyncio.CancelledError` propagates through `await` but not through synchronous code.

**How to avoid:**
- Implement `messages()` as a proper `async def` generator with `try/finally` that always closes the underlying WebSocket and signals the recorder to flush.
- Add a `close()` async method and an `async with` context manager (`async with NLSClient(...) as client:`) for explicit lifecycle management.
- Test cancellation: have a test that starts the iterator, breaks after 5 messages, and asserts the WS is closed within 1s.
- Use `asyncio.shield()` for the recorder's flush operation so it completes even if the main task is cancelled.

**Warning signs:**
- "Address already in use" or "connection refused" on the second `connect()` after a cancellation
- Recorder file is missing the last N messages when the consumer cancels
- WebSocket count (per server) doesn't drop when consumers exit

**Phase to address:**
Transport phase + recorder phase.

---

### Pitfall 9: Schema changes between seasons

**What goes wrong:**
The protocol has no version field. `VER` and `EXPORTID` are *event* identifiers, not schema identifiers. The 2026 season may add a new field to `RESULT`, rename a sector field, or split a single PID into two. A library that hard-codes field names breaks the next season.

**Why it happens:**
The server is undocumented and reverse-engineered. There is no contract to break — it just changes.

**How to avoid:**
- Every model class uses `extras: dict[str, Any] = field(default_factory=dict)` to capture unknown fields. These are exposed via `car.extras.get("new_field_2027")` so consumers can opt in to new fields without library updates.
- PIDs without a registered handler produce an `UnknownMessage(pid=..., raw=...)` object instead of raising. Surface these on the event stream so consumers see *what changed*.
- Add a `NLSProtocolVersion` constant in the library. When schema drift is observed, bump it and emit a `ProtocolWarning`. Document the upgrade procedure.
- Record the raw JSONL alongside the parsed version so an old library can be re-run against a new race's log.
- Subscribe to a few "schema sentinel" PIDs (1, 2, 5, 6, 8-500, 502-9001, 9003+) during development to discover new fields as the server adds them.

**Warning signs:**
- New field appears in `RESULT` but doesn't make it into the typed model
- Car's `extras` grows monotonically across seasons (indicates schema drift)
- Test suite passes against 2025 logs but fails against 2026 logs

**Phase to address:**
Parser phase + cache phase. The `extras` pattern is a model concern; the `UnknownMessage` handling is a dispatcher concern.

---

### Pitfall 10: Replay parity with live mode

**What goes wrong:**
The library promises that live and replay share one API surface. But there are subtle differences:
- Live: messages arrive in real time, with gaps of milliseconds to seconds.
- Replay: messages arrive as fast as the disk reads them, possibly thousands per second.
- Live: time-sync messages arrive periodically. Replay: they should be suppressed (or replayed with their original timestamps) but not collapsed.
- Live: reconnect happens at the transport layer. Replay: reconnect is a non-event.
- Live: cache mutations are time-ordered. Replay: if the JSONL is out of order, the cache ends up wrong.

**Why it happens:**
A unified API makes consumers think replay and live are interchangeable. They are *almost* interchangeable but the time semantics differ.

**How to avoid:**
- Introduce a `Source` enum: `LIVE`, `REPLAY`, `IMPORTED`. Surface it on the client object. Document the differences.
- For replay, expose a `replay_speed` parameter (default 1.0 = real-time) and a `replay_now` (simulated wall-clock) for consumers that want to drive a dashboard from historical data.
- Treat time-sync messages in replay as *informational*, not state-mutating. They update an internal clock but don't dispatch to the public event stream (or do dispatch to a separate stream).
- When loading from JSONL, validate the file: each line must be valid JSON, in order, and the first message must be a known PID (0) or a sentinel.
- Document that the cache's *ordering invariant* holds for both sources: applying messages in JSONL order must produce the same cache state as applying them in real time.

**Warning signs:**
- Cache diverges between live and replay of the same race
- Replay processes messages 100x faster than real time and saturates the event loop
- Consumers can't tell whether they're in live or replay mode (this is fine; consumers shouldn't have to care — but the library must know)

**Phase to address:**
Recorder phase + cache phase + parser phase. The shared API surface must be designed before any phase implements it.

---

### Pitfall 11: Stale cache after WS disconnect

**What goes wrong:**
The WebSocket drops for 30 seconds, reconnects, and the cache still shows the *pre-disconnect* state. New messages start arriving but the consumer has no signal that the cache is stale relative to reality.

**Why it happens:**
No "full state" message exists in the protocol after the initial handshake. PID 0 is sent only on the very first connect. On reconnect, the server resumes streaming PID 3/4/7/501/9002 from wherever the live feed is — there is no replay of missed PID 0.

**How it matters:**
During the 30s gap, a car might have pitted, lapped multiple cars, or received a penalty. The reconnect state is missing all of that. Applying new messages on top of stale cache creates a Frankenstein.

**How to avoid:**
- On reconnect, mark the cache as `STALE` until a full re-subscription has been confirmed.
- Implement `clear()` and call it on reconnect (or expose a `reconcile` policy: keep / clear / reset-keys).
- Document the cache freshness contract explicitly: `cache.freshness` is `FRESH`, `STALE`, or `RESYNCING`.
- HA sensors reading from the cache should use `cache.freshness` to determine whether to publish `unknown` instead of stale data.

**Warning signs:**
- A car that pitted before the disconnect still shows `in_pit=False` after reconnect
- Sector time appears to go backward
- HA automation fires on stale data

**Phase to address:**
Cache phase + transport phase.

---

### Pitfall 12: File rotation and partial JSONL during long races

**What goes wrong:**
An NLS race weekend can run 8+ hours of continuous streaming. A single JSONL file grows unbounded. The recorder crashes when the disk fills up. The replay of a partially written JSONL fails because the last line is truncated.

**Why it happens:**
No file size limit in the default recorder. No graceful truncation handling in the replay loader.

**How to avoid:**
- Implement automatic file rotation: by size (default 100 MB) or by time (default hourly). Each rotated segment is named `race_2026-06-20_NLS3_<timestamp>.jsonl`.
- On replay, detect partial trailing lines (no newline, or invalid JSON) and skip with a warning rather than crash.
- Add a `flush()` method that the recorder's task calls every N seconds so even an unclean shutdown loses at most N seconds of data.
- Document the recommended file layout in the recorder's docstring.

**Warning signs:**
- Recorder crashes at hour 7 with `OSError: No space left on device`
- Replay of a real race produces a `JSONDecodeError` on the last line
- Single 5 GB JSONL file is unreadable by `jq` or other tools

**Phase to address:**
Recorder phase.

---

### Pitfall 13: Memory growth in the per-car laps cache

**What goes wrong:**
Channel 7 (`{ session, startingNo }`) streams per-car lap data. Each car does 30-40 laps in a typical NLS race. A race has ~100 cars. If the cache keeps every lap for every car in memory, that's ~4000 lap records per session — not a problem. But *across* sessions, weekends, or replay runs, the cache grows without bound.

**Why it happens:**
No LRU policy, no session-keyed reset, no max size.

**How to avoid:**
- The cache must be keyed by `session_id` (or `event_id + session_number`) so it's natural to drop an entire session at once.
- Per-car laps are bounded by the number of cars × number of laps in a session. Document this bound.
- The library should expose a `cache.stats()` method showing memory use (rough estimate: object count) so consumers can monitor.
- Add a `clear(session=...)` method for selective drop.

**Warning signs:**
- Process RSS grows from 50 MB to 500 MB over a 4-hour race
- Replay of multiple races in one process causes OOM

**Phase to address:**
Cache phase.

---

### Pitfall 14: HA event loop blocking — the silent killer

**What goes wrong:**
Home Assistant runs on a single event loop. If this library does any sync I/O on HA's event loop — even briefly — HA's UI freezes, automations stop, and the HA watchdog logs "blocking call" warnings. The library will appear to work in a standalone script but break inside HA.

**Why it happens:**
The library is async-first but consumers may pass sync callbacks, use sync context managers, or import the library in a sync code path. Even `__init__` that reads a config file synchronously will block.

**How to avoid:**
- **No HA imports in the core package** (per PROJECT.md constraint). This is the rule that prevents transitive HA coupling.
- All public methods must be `async def`. Sync helpers go in a `nls_cli` or `nls_sync` separate package.
- The library's own event loop is *managed internally*: `NLSClient.start()` returns a task; the consumer is responsible for scheduling it. Do not use `asyncio.get_event_loop()` (deprecated in 3.12+).
- HA consumers should use HA's `hass.async_add_executor_job` for any sync helper the library exposes (e.g., exporting to JSON file).
- Document the "no sync in the hot path" rule prominently in the README. HA devs will read it.

**Warning signs:**
- "Detected blocking call" warnings in HA logs when the NLS integration runs
- HA UI freezes for 200-500 ms during a high-frequency update burst
- HA's `execute_script` for NLS-related triggers times out

**Phase to address:**
Transport phase + cache phase + distribution phase.

---

### Pitfall 15: PyPI packaging — optional deps and Python version

**What goes wrong:**
- The library uses `websockets` for WS, `aiohttp` for HTTP, `orjson` for fast JSON. All three are core deps, not optional. A `pip install aio-nls-livetiming` should pull them all.
- But `orjson` has native wheels for most platforms but not all (some exotic Linux distros require a Rust toolchain). Listing it as a hard dep may break installs on those platforms.
- HA requires Python 3.12+ as of late 2025 (HA Core 2025.12+). The library's `python_requires=">=3.10"` from PROJECT.md is too permissive — it installs on 3.10 but consumers using it inside HA will get a version mismatch.

**Why it happens:**
Easy to set the lower bound too low for "maximum compatibility" and ship a library that HA can't actually use.

**How to avoid:**
- `python_requires=">=3.12"` in `pyproject.toml`. Document this prominently. The async generators + TaskGroup features used internally need 3.12.
- Make `orjson` an optional dependency. Fall back to stdlib `json` if not installed. The 5-10x speedup matters for the recorder but not for consumers reading cached state.
- Use `pyproject.toml` only (PEP 621). No `setup.py`, no `setup.cfg`. Modern packaging.
- Use `hatchling` or `uv build` as the build backend — both are HA-friendly.
- Pin `websockets>=12.0` (the version that fixed the `ping_interval=None` semantics).
- Provide type hints everywhere; mark the package as `py.typed` so mypy/pyright work in HA's strict type-check environment.

**Warning signs:**
- HA rejects the package because of Python version
- Install fails on Alpine Linux (musl wheel missing)
- mypy errors in HA consumers because the library's types are imprecise

**Phase to address:**
Distribution phase — the final phase before release.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hard-code PID values as integers (e.g., `if pid == 0`) | Fast to write | Brittle to PID reuse or new PIDs; hides meaning | Never — use `Pid` enum |
| Re-parse the entire cache on every reconnect | Simpler code | O(N) cost on every blip, plus a STALE window | Never — use targeted re-subscription |
| Store cache as `dict[str, Any]` | No schema work | No type safety, no `extras` mechanism, schema drift hides | Never — dataclasses with `extras` are not expensive |
| Single global cache for all sessions | Less code | Cross-session contamination, OOM risk | Never — key by session |
| Use `json.dumps` for the recorder | Stdlib only | 5-10x slower; blocks event loop on large payloads | Only when `orjson` install fails; document the fallback |
| Suppress reconnect errors silently | Cleaner logs | Consumers can't tell if the feed is healthy | Never — at minimum count and log at debug |
| Sync `__init__` that reads a config file | Easier API | Blocks HA's event loop | Never — accept config as a parameter, not via I/O |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `websockets` library | Letting the library drive pings (`ping_interval=20`) | Set `ping_interval=None` and drive heartbeats from the time-sync messages |
| `websockets` library | Not handling `ConnectionClosed` distinctly from `InvalidStatusCode` | Catch them separately; 1006 = idle timeout, others = auth/server error |
| Azure App Service | Assuming WebSocket survives idle | Build app-level keepalive; never rely on TCP keepalive alone |
| Azure App Service | Reconnecting immediately on close | Backoff with jitter; honor Retry-After |
| `orjson` | Catching `ImportError` everywhere | Use a module-level `try/except` and bind `_dumps = orjson.dumps` once |
| `aiohttp` | Using `ClientSession()` per request | Reuse a session; HA consumers should pass in HA's `async_get_clientsession(hass)` |
| HA custom component | Importing HA modules from the core library | Keep HA imports in a separate `nls_livetiming.ha` shim package |
| JSONL replay | Treating the file as a stream with `for line in f:` | Validate header (PID 0 expected first), validate ordering, handle partial trailing line |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Stdlib `json.dumps` on hot path | Event loop warnings, lag | Use `orjson` (5-10x faster) | When message rate > 50/s |
| Cache uses `dict` of `dict` without keys | Memory growth | Use dataclasses with `__slots__` | At 10k cars in cache (unusual but possible across seasons) |
| Reconnecting on every 1006 close | Reconnect storms during Azure maintenance | Backoff with jitter, max 1 reconnect per 5s | When 100+ consumers run in parallel |
| Recorder uses sync file I/O | Disk-bound lag | Async queue + dedicated writer task | When disk is slow (network mount, encrypted FS) |
| Per-message `extras: dict` allocation | CPU overhead | Use `MappingProxyType` for read-only access | At 1000 msg/s |
| `messages()` yields individual messages | Consumer task overhead per item | Batch yields (e.g., `async for batch in client.message_batches():`) | At 500+ msg/s |
| Filter query iterates the entire cache every call | Latency spikes during high message rate | Maintain sorted indexes (by class, by position) | At >100 cars in cache |

## Security Mistakes

Domain-specific, beyond OWASP basics.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging the full WebSocket handshake (which may include `eventId` that can be guessed) | Targeted DoS against a specific race | Log `eventId` at debug only; redact in info |
| Storing the JSONL log in a world-readable location | Reveals race results before the official results are published | Recommend `chmod 600` in the recorder docs; consumer's responsibility |
| Hardcoding the Azure App Service URL in the library | Single point of failure if Azure region goes down | Make the URL a constructor parameter; default to the current URL |
| Trusting the `LTS_NOT_FOUND` semantics without verification | Server bug or attack could lock the consumer out | Configurable behavior; default to "retry on not_yet_started, give up on ended" |
| Recording PII from race messages (driver names, team names) without consent | GDPR concerns for EU consumers | Document that the recorder may contain PII; consumers must handle per their jurisdiction |

## UX Pitfalls

Common developer-facing experience mistakes when wrapping an undocumented protocol.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Library crashes on first unknown PID | Consumer can't even connect to a new season | Surface `UnknownMessage` and continue |
| Library silently swallows dropped messages | Cache drifts, no signal | `cache.skipped_messages` counter + `WARNING` log |
| Library has no way to inject a mock time source | Can't unit test replay | Inject `time_source: Callable[[], float]` into the client |
| Library's `messages()` returns raw dicts | Consumers must re-parse | Return typed `Message` dataclass variants (one per PID) |
| Library mixes time-sync messages with race messages | Consumers pollute their event logs | Separate `messages()` and `time_sync()` iterators |
| Library has no `__repr__` on cache objects | Debugging in a REPL is painful | `__repr__` returning a compact summary on every public model |
| Library requires constructing the client in a specific order | Consumer writes try/except for config | Use a single `NLSClient.create(event_id=...)` factory method |
| Library's async API differs slightly between live and replay | Consumers fork their code | One `Source` enum, one event stream API, one cache, documented differences |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **WebSocket transport:** Often missing app-level keepalive — verify a synthetic heartbeat (using the time-sync message) keeps the connection alive through a 5-minute quiet stretch.
- [ ] **Parser:** Often missing `extras` capture — verify an unknown field on `RESULT` lands in `car.extras`, not silently dropped.
- [ ] **Cache:** Often missing idempotency — verify applying the same `(startingNo, lap, sector)` tuple twice is a no-op.
- [ ] **Cache:** Often missing freshness tracking — verify `cache.freshness` transitions to `STALE` on disconnect and back to `FRESH` after re-subscription confirms.
- [ ] **Recorder:** Often missing partial-trailing-line handling — verify a JSONL file ending in a truncated line replays gracefully with a warning.
- [ ] **Replay:** Often missing JSONL ordering validation — verify out-of-order lines are rejected with a clear error.
- [ ] **Replay:** Often missing time-sync suppression — verify replay's `messages()` iterator does not yield time-sync events.
- [ ] **HA integration:** Often missing the executor-job boundary — verify no sync I/O runs on HA's event loop (smoke test: HA UI does not freeze during a 30-second high-frequency burst).
- [ ] **Distribution:** Often missing `py.typed` — verify `mypy --strict` works on a downstream consumer.
- [ ] **Distribution:** Often missing the `orjson` fallback — verify the library installs and works on a system without `orjson` (fall back to stdlib `json`).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Azure idle timeout closes WS | LOW | App-level keepalive; no consumer action needed |
| Dropped message | LOW | Reconnect; clear cache; resubscribe (cache converges eventually) |
| Schema drift (new field) | MEDIUM | Add field to model; bump internal protocol version; consumers read `extras` until they update |
| Session transition (mid-session) | MEDIUM | `cache.clear()` + reconnect; consumer must handle the gap |
| Reconnect storm | LOW | Backoff with jitter; library self-corrects within 60s |
| Recorder file corruption | MEDIUM | Rotate file; replay tolerates last-line truncation; consumer reruns replay |
| Cache diverges between live and replay | HIGH | Diagnose ordering; may need to invalidate cache and re-replay |
| HA event loop block | HIGH | Identify the sync call (usually `json.dumps` or file write); refactor to async-isolate |
| OOM in cache | MEDIUM | Add `cache.clear(session=...)`; review retention policy |
| PyPI install fails on musl | LOW | Make `orjson` optional; fall back to stdlib `json` |
| HA rejects library due to Python version | LOW | Bump `python_requires`; document |

## Pitfall-to-Phase Mapping

How roadmap phases should prevent these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Azure idle timeout | Transport phase | Unit test: simulate 5-min silence, verify no reconnect |
| Time-sync message pollution | Parser phase | Unit test: feed `{ type: "time", value: 1 }`, verify it does not enter cache |
| Dropped/duplicated messages | Cache phase | Unit test: apply same tuple twice, verify no duplicate state |
| Session transitions crash | Parser phase + Cache phase | Unit test: replay qualifying→race transition, verify cache resets |
| LTS_NOT_FOUND ambiguity | Parser phase + Transport phase | Unit test: feed all three forms, verify distinct behavior |
| Reconnect storms | Transport phase | Unit test: simulate 100 concurrent reconnects, verify jitter |
| Blocking I/O on event loop | Cache phase + Recorder phase | Unit test: measure `slow_callback_duration` during 30s of recording |
| Cancellation safety | Transport phase + Recorder phase | Unit test: cancel mid-iteration, verify WS closes within 1s |
| Schema drift | Parser phase | Unit test: feed an unknown field, verify it lands in `extras` |
| Replay parity | Recorder phase + Cache phase | Test: same JSONL replayed twice produces identical cache state |
| Stale cache after disconnect | Cache phase + Transport phase | Unit test: simulate disconnect + reconnect, verify `freshness` transitions |
| File rotation | Recorder phase | Test: simulate 8-hour race, verify file rotation works |
| Memory growth | Cache phase | Test: replay 10 races, verify RSS stabilizes |
| HA event loop block | Transport phase + Cache phase + Distribution phase | HA smoke test: no "blocking call" warnings during 30s burst |
| PyPI packaging | Distribution phase | Test: `pip install` on Alpine, on macOS, on Windows; `mypy --strict` on consumer |

## Sources

- PROJECT.md — reverse-engineering notes from inspecting `leaderboard.e24a.bundle.js`, `lapsData.0179.bundle.js`, `vendor.aec0.bundle.js` (July 2026 inspection date)
- Azure App Service documentation on WebSocket idle timeout (well-known ARR behavior; verified across multiple MS docs and GitHub issues)
- Python `websockets` library docs — `ping_interval`, `close_timeout`, `ConnectionClosed` semantics
- Python `asyncio` docs — `async` generators, `aclose()`, `CancelledError` propagation (3.7+ to 3.12+)
- Home Assistant developer docs — async-first integration patterns, event-loop blocking warnings, Python 3.12 requirement (HA Core 2025.12+)
- PyPA `pyproject.toml` guide (PEP 621) — modern packaging
- `orjson` README — performance characteristics vs stdlib `json`
- Personal experience with Azure App Service WebSocket idle timeouts (well-documented gotcha in any long-lived WS client on Azure)

---
*Pitfalls research for: AIO NLS Livetiming API*
*Researched: 2026-06-20*