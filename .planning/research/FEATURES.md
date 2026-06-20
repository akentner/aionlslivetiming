# Feature Research — AIO NLS Livetiming API

**Domain:** Async-first Python client library wrapping a real-time motorsport WebSocket feed (NLS livetiming service).
**Researched:** 2026-06-20
**Confidence:** **MEDIUM-HIGH** — validated against FastF1 (5.2k★, MIT) as the canonical reference, plus direct knowledge of NLS bundle reverse-engineering in PROJECT.md. WebSearch/Brave unavailable in this environment, so cross-library comparison is narrower than ideal; findings on FastF1 are HIGH confidence, claims about NLS feed shape are HIGH confidence (own reverse engineering), competitive claims are MEDIUM.

---

## Executive Summary

The user has already locked in the strategic direction: build a **clean async-first Python client** that exposes **the same API surface** for both **live** and **replay** (driven from a recorded JSONL log), and ship the recording + replay + cache + filter combo as the **differentiator**. This research validates that direction against the closest comparable library — **FastF1** — and concludes the user's feature set is correct and well-targeted. Two refinements are recommended: (1) keep the **cache** simple (in-memory, identity-mapped state, not a pickle filesystem like FastF1), because NLS has no API rate limits; (2) make the **filter** API first-class (not bolted onto a pandas accessor) because the user already plans to consume from bots/dashboards that don't want pandas.

The feature landscape splits naturally into three layers that should map to phases:

1. **Connect & parse** — table stakes; without this, nothing else works.
2. **Cache & query** — table stakes; a downstream bot that has to reimplement state would be useless.
3. **Record, replay, export/import** — the differentiators; what makes this library worth publishing instead of just inlining the WS code in each downstream project.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features any sports-timing client library must expose or downstream projects can't use it. Missing these = the library is broken or pointless.

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| T1 | **Async WebSocket connect + handshake by event id** | The whole point of the library is to wrap `livetiming.azurewebsites.net`. If a user has to write their own `websockets.connect(...)` they don't need the library. | LOW | PROJECT.md already specifies the handshake shape. FastF1's `SignalRClient` is the analogue. |
| T2 | **Per-channel subscribe** (results/3/7/501/9002) | The WS is multiplexed; the user must be able to opt into channels. FastF1 does this implicitly by topic. | LOW | Matches PROJECT.md active requirements. |
| T3 | **Typed decoder for every short-code field** (PID, EXPORTID, SESSION, CUP, HEAT, HEATTYPE, TRACKNAME, STQ, BEST, TOD, RESULT, LTS_NOT_FOUND) | "Decoding the short-code JSON into typed objects" is an explicit PROJECT.md requirement. Without it, the library only moves bytes. | MEDIUM | Needs a parser module per PID. Tolerant of unknown fields per PROJECT.md "Known issues". |
| T4 | **UnknownPID / UnknownMessage surfacing** | "Schema can change between seasons. Mitigate by versioning the parser internally and surfacing unknown PIDs as `UnknownMessage` rather than crashing." — explicit in PROJECT.md. | LOW | One exception class + per-channel handler that catches unknown PIDs. |
| T5 | **Async message stream API** (`async for msg in client.messages(): ...`) | Explicit PROJECT.md requirement. Standard async pattern. | LOW | FastF1's live client does not actually expose an async stream (it only records to file and replays after) — the user's choice of async-first + live streaming is more flexible than FastF1. |
| T6 | **Reconnect with backoff** | The bundle has a "thin reconnection wrapper" with 1s backoff, retries on 1000/1001/1005, exposes `onreconnect`/`onmaximum`. Without this the library is fragile on flaky home networks. | LOW-MEDIUM | Project context says the vendor already has the pattern; the library can re-implement it. |
| T7 | **Exception hierarchy** (`NLSTimeoutError`, `NLSConnectionError`, `NLSParserError`, `NLSUnknownPIDError`) | FastF1 has a full exception tree (`FastF1CriticalError`, `RateLimitExceededError`, `DataNotLoadedError`, `NoLapDataError`). Without an exception tree, every consumer writes the same `try/except` mess. | LOW | One base class + a small set of subclasses. |
| T8 | **In-memory queryable cache** (current standings, per-car lap history, race messages, qualifying, statistics) | Explicit PROJECT.md requirement: "Maintain a queryable cached state". Without it, consumers rebuild state from the stream themselves. | MEDIUM | Maps incoming messages to dicts keyed by starting number / session. Idempotent merge because PROJECT.md warns "server can drop messages… cached state must converge idempotently". |
| T9 | **Per-car lap drilldown via `GET /event/{id}/laps-data`** (or via channel 7) | Explicit PROJECT.md requirement. Note: PROJECT.md discovered that `/laps-data` returns HTML, so the per-car detail should come from channel `7` instead. | LOW | Just needs to subscribe to channel 7 and merge the per-car data into the cache. |
| T10 | **`async with` lifecycle (start, close, context manager)** | Every async library needs a clean shutdown path. FastF1's `SignalRClient.start()` is the synchronous equivalent. | LOW | The recorder/file handle and the WebSocket both need deterministic cleanup. |
| T11 | **Type hints throughout the public API** | Modern async Python libraries (`httpx`, `aiohttp`, FastF1) are typed. Project context: "type hints, MIT-licensed" is explicit. | LOW | Use `dataclass` / `TypedDict` / `pydantic` (decision belongs to STACK.md). |
| T12 | **CLI entry point** for recording without writing a script | FastF1 ships `python -m fastf1.livetiming save out.txt`. Users running this on a Raspberry Pi at race day want one command, not a script. | LOW | Tiny `python -m aionlslivetiming record <event_id> <file>`. |
| T13 | **Structured logging** | FastF1 ships a `Logging` doc page. Reconnect storms, dropped messages, unknown PIDs — these are debug events. The user already uses `logging`-aware code across their open-source work (CLAUDE.md mentions `loglevel` is configured). | LOW | Library emits to stdlib `logging.getLogger("aionlslivetiming")`. |

**Table-stakes assessment:** T1-T4 + T8 + T10 are the absolute minimum for the library to be usable. T5 + T6 + T7 are the cost of being a competent async library. T11-T13 are the cost of being a *publishable* async library. None of these are "wow" features; they are simply what the user is paying for when they pick a library over inline code.

---

### Differentiators (Competitive Advantage)

Features that go beyond the bare WebSocket and make the library worth installing. These are explicitly in PROJECT.md and validated against FastF1's `livetiming` subpackage.

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| D1 | **Record raw WS stream to JSONL** | Lets users develop against historical races. The NLS feed is "only live during a race event; replay/log support is essential" (PROJECT.md). FastF1 does exactly this with its `SignalRClient(filename=...)` and `--append` / `--debug` flags. | LOW | The recorder is just a tee off the message stream. PROJECT.md already says "JSONL for the recorder". |
| D2 | **Replay a recorded JSONL log through the same API surface as a live connection** | "Live and replay share one API surface" is a key PROJECT.md decision. Without it, every consumer has to branch. | LOW-MEDIUM | Same parser, same cache, same event stream — only the source differs. FastF1 separates the live `SignalRClient` and the `LiveTimingData` replay object; this is a reasonable shape but the user wants the **same** object, which is a stronger guarantee. |
| D3 | **Filter the cached state by car class, starting number, driver, position range, lap range, sector time** | Explicit PROJECT.md requirement. Lets a Discord bot say "give me the AT class, top 5" or "give me car #42's pit history" without scanning everything. | MEDIUM | Pure read API over the cache; no extra state. Validated by FastF1's `Laps.pick_track_status`, `.pick_wo_box()`, `.pick_driver()`, etc. — this is the established shape. |
| D4 | **Export cached state + recorded log to JSON / JSONL** | Explicit PROJECT.md requirement. Lets users share recordings with other users, attach them to bug reports, archive seasons. | LOW | One function per format. State = JSON (nested), log = JSONL (line-delimited). |
| D5 | **Import state and logs from JSON / JSONL** | Explicit PROJECT.md requirement. Symmetric to D4. Lets users restore from a saved state snapshot. | LOW | Inverse of D4. |
| D6 | **Clear and reset the in-memory cache on demand** | Explicit PROJECT.md requirement. Replay from t=0 cleanly without restarting the process. | LOW | One method on the client. |
| D7 | **Race-control event stream (parsed messages)** | The library already decodes channel 3; surfacing those as `RaceMessage` events (pit, flag, penalty, sector best) is a typed event the user can `await` on. PROJECT.md lists "pit messages" as a data the consumer wants. | LOW | A subclass of `Message` and an `async for msg in client.race_messages():` iterator. |
| D8 | **Live + replay parity (transparent mode switch)** | The strongest differentiator vs FastF1: FastF1 forces the user to call `session.load(livedata=LiveTimingData(...))` for replay and `SignalRClient.start()` for live. The user wants a *single* `NLSClient` that takes a `source=` argument and otherwise behaves identically. | LOW | Construct either a live source or a file source; the rest of the client is the same. |
| D9 | **Home-Assistant-friendly (no HA imports, MIT, async-first)** | Explicit PROJECT.md requirement: "drop-in async library for Home Assistant custom components (no HA-specific imports in the core package)". The user maintains HA infra. | LOW | Constraint, not a feature — but it filters out a number of alternative designs. |

**Differentiation assessment:** The **recording + replay + cache + filter** combo is exactly what the user picked. Compared to FastF1, this library is **simpler** (no pandas, no Ergast, no telemetry, no plotting) and **more focused** (one source, one mode, async-first). That is a defensible position: a small, fast, focused library for *one* timing feed, with a development story that does not require waiting for the next race weekend.

---

### Anti-Features (Commonly Requested, Often Problematic)

Features that look attractive but would either blow the scope, tie the library to the wrong shape, or pull in dependencies the user has already excluded.

| # | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|--------------|---------------|-----------------|-------------|
| A1 | **pandas DataFrame as the primary data type** | "It's how FastF1 does it" — every F1 library has a DataFrame API because pandas is the lingua franca of data analysis. | Forces pandas on every consumer (Discord bots, HA, dashboards don't need it); adds a heavy dependency; hides the typed-object model the library is actually built on. PROJECT.md says "asyncio/aiohttp, no blocking I/O on the hot path" — pandas on the hot path violates that for the data shape. | Expose typed objects (dataclasses) in the public API; optionally provide a `to_pandas()` adapter as a separate opt-in submodule if anyone needs it. |
| A2 | **File-based stage-2 cache (pickle + sqlite, like FastF1's `Cache`)** | "It's standard" — FastF1 has it, requests-cache is popular. | The NLS feed has **no rate limits** and is **public** — there is no API to protect. A filesystem cache adds complexity (cache invalidation, `force_renew`, separate cache dirs for live vs replay data per FastF1's own docs) for no benefit. | Skip the persistent cache in v1. The in-memory cache (T8) is enough. If a user wants to archive, they use D4 (export to JSON). |
| A3 | **Authentication (login flow, F1TV-style account)** | "Other timing libraries need accounts" — F1's livetiming needs an F1TV Pro subscription; users assume the same shape. | "Authentication against any logged-in NLS endpoints (the livetiming service is currently public)" is **explicitly Out of Scope** in PROJECT.md. The feed has no auth — adding it is dead code. | Don't build it. If NLS adds auth later, add a `NLSClient(event_id=..., token=...)` kwarg then. |
| A4 | **Telemetry data (car speed, RPM, gear, position traces)** | This is what FastF1 is famous for; users will assume it's there. | NLS publishes **timing only** — no per-sample telemetry on the WS. Telemetry is F1-specific data; including it in the API surface would be confusing and would never return data. | Don't ship a `Telemetry` accessor. The `STQ`/`BEST` fields give speed at best-sector; that is what NLS exposes. |
| A5 | **Ergast / Jolpica-style external REST API wrapper** | FastF1 ships both livetiming and a separate Ergast wrapper. | There is no equivalent public REST API for NLS. The closest is `/event/{id}/laps-data` which (per PROJECT.md reverse engineering) returns HTML, not JSON. | Drop it. The channel-7 subscription covers per-car data. |
| A6 | **Plotting / Matplotlib integration** | "FastF1 does it" — every analysis library has plots. | The user is a *consumer* of NLS data (bots, dashboards, HA), not a *visualizer* of it. Plotting is downstream concern. | Don't ship `plotting.*`. If someone wants plots, they can take a dataclass and matplotlib it themselves. |
| A7 | **Multi-series support (WEC, IMSA, NLS, etc.)** | "Other series also have livetiming" — could be a multi-series library. | Each series has its own bundle, schema, and quirks. Trying to support more than one turns the clean NLS client into a "weird thin wrapper over N different vendors' bad designs." PROJECT.md is explicit: NLS only. | Single-series library. If WEC/IMSA users want a similar tool, they fork or build a sibling. |
| A8 | **Server-push race state reconstruction (auto-rebuild full state from a single API request)** | Some libraries (e.g., legacy F1 timing APIs) have a "give me the full state right now" endpoint. | NLS does not have one — the state is only available incrementally over the WS. Users would assume this exists and get a 404. | Document that the cache starts empty and converges from the stream. `D6` (clear cache) is the reset story. |
| A9 | **Persistent database backend (SQLite/Postgres for state)** | "Powerful" — easy to query across races. | PROJECT.md is explicit: "Persistent storage beyond files (no DB requirement in v1)". Adds a dep, adds migrations, adds schema design work. | Use JSON export (D4) for archiving. |
| A10 | **Real-time push notifications (mobile push, email, webhook)** | "Users want to know when their car pits" — natural extension. | Out of library scope — that's a consumer (Discord bot, HA) job. Adds webhook config, secrets, retry logic to what should be a feed wrapper. | Let consumers subscribe to the message stream and notify from there. |
| A11 | **Web dashboard / UI** | "Other libraries have dashboards" — FastF1 users often visualize in Jupyter. | PROJECT.md is explicit Out of Scope: "Building a UI / web frontend". The user is a *consumer* library. | Skip. Jupyter notebooks on top of the typed API are a downstream concern. |
| A12 | **Outcome prediction / ML features** | "We have all the data, let's predict lap times." | PROJECT.md is explicit Out of Scope: "Predicting / forecasting race outcomes (only consume what the server publishes)". And the data set per race is tiny — single-digit MB. | Don't ship ML. Consumers can train on exported JSONL if they want. |
| A13 | **A pre-built sync wrapper** (`NLSClientSync` for non-async callers) | "Some users can't be async" — fair point. | Doubles the API surface; the entire client (recorder, replay, cache) is stateful and async — a sync wrapper would just block a thread. Most Python async libraries (httpx, aiohttp) explicitly say "use asyncio.run". | Document the `asyncio.run(...)` pattern. The user is a heavy asyncio user already (HA, aiohttp). |
| A14 | **Fancy schema migration / version negotiation** | "What if the server changes PIDs?" | Tolerant parsing (T4) covers this. A full schema-negotiation system is over-engineering for one feed. | Per-PID handlers + `UnknownMessage` fallback. Bump a `PARSER_VERSION` constant. |

**Anti-feature rationale:** A1, A2, A6, A7, A9, A11, A12 are all anti-features FastF1 has *deliberately chosen to include* because their target audience is F1 data analysts. The user's audience (HA, Discord bots, dashboards) is fundamentally different — they want a small, typed, async surface. The anti-features above are "what you do if you're building a data-science library" — that is not this project.

---

## Feature Dependencies

```
T1 Connect + handshake
   └──requires──> T10 async context manager
                   └──requires──> T6 Reconnect with backoff

T2 Per-channel subscribe
   └──requires──> T1

T3 Typed decoder
   ├──requires──> T2 (raw messages to decode)
   └──requires──> T4 UnknownPID handling (so a schema break doesn't crash)

T5 async message stream
   └──requires──> T3 (typed messages to stream)
       └──requires──> T8 in-memory cache
                       └──requires──> T3

T7 Exception hierarchy
   └──requires──> T1, T3 (exceptions raised on connect/parse)

T8 In-memory cache
   ├──requires──> T3
   └──requires──> T9 per-car lap drilldown (PID 7)

T9 Per-car lap drilldown
   └──requires──> T2 (subscribe to channel 7)

T11 Type hints
   └──requires──> T3 (types defined with the decoder)

T12 CLI entry point
   └──requires──> D1 recorder (CLI just records)

T13 Structured logging
   └──enhances──> T6 (reconnect events)
                ──enhances──> T4 (unknown PID warnings)

D1 Record to JSONL
   └──requires──> T5 (tee off the stream)
                  T12 (CLI is the common entry point)

D2 Replay from JSONL
   ├──requires──> T3 (same parser as live)
   └──requires──> T8 (same cache as live)

D8 Live + replay parity
   ├──requires──> T1 (live source)
   └──requires──> D2 (file source)
                   └──conflicts──> no other shape — single object only

D3 Filter the cache
   └──requires──> T8 (cache to filter)
                  T3 (typed objects to filter by)

D4 Export state + log
   └──requires──> T8 (state to export)
                  D1 (log to export)

D5 Import state + log
   └──requires──> T8 (cache to populate)
                  D1 (log to re-emit)

D6 Clear cache
   └──requires──> T8 (cache to clear)

D7 Race-control event stream
   └──requires──> T3 (parsed race-control messages)
                  T5 (stream API)
```

### Dependency Notes

- **T1 → T10 → T6:** the WebSocket lifecycle owns reconnect; you can't reconnect cleanly without a context manager that handles both happy and unhappy paths.
- **T3 → T4:** typed decoding without a tolerant unknown-PID escape hatch will crash on the first schema change. **They must ship together.**
- **T3 → T5 → T8:** the cache only works if both the stream and the parser are right. Cache without parser = `dict[str, Any]`. Parser without cache = every consumer rebuilds state.
- **D1 → D2 → D8:** the live + replay parity story is impossible without both recorder and replay, and is most valuable as a *single* client object that hides the source.
- **D3 → T8:** "filter the cache" only makes sense once there *is* a cache. Filter is read-only and stateless.
- **D4 ↔ D5:** export/import are a pair; if you ship one without the other, the round-trip story is broken.
- **D6 → T8:** clear cache is a method on the cache; it has no value without one.
- **D7 → T3 + T5:** race-control events are a typed projection of channel-3 messages through the stream. A nice differentiator because it is a typed async iterator instead of "scan the cache for messages".

### Conflicts

There are no hard conflicts between any features in the table. The closest thing to a conflict is **A1 (pandas as primary type)** vs **T3 (typed dataclasses)** — choosing pandas for the API surface means you can't have first-class typed objects. The recommended resolution is "typed objects primary, optional pandas adapter in a separate optional submodule if a user requests it." This is a deferred-conflict (doesn't bite v1) and is recorded here so the roadmap doesn't accidentally pull pandas in.

---

## MVP Definition

### Launch With (v1)

The minimum that lets a downstream project (Discord bot, HA, dashboard) actually use the library.

- [x] **T1, T2, T6, T10** — connect, subscribe, reconnect, async lifecycle
- [x] **T3, T4** — typed decoder + tolerant unknown-PID
- [x] **T5, T7** — async message stream + exception hierarchy
- [x] **T8, T9, D6, D3** — in-memory cache, per-car drilldown, clear cache, filter
- [x] **D1, D2, D8** — record, replay, live+replay parity
- [x] **T11** — type hints
- [x] **T12** — `python -m aionlslivetiming record` CLI
- [x] **T13** — `logging.getLogger("aionlslivetiming")`
- [x] **D7** — race-control event stream (cheap; just a typed projection)

**Out of MVP** (D4, D5) — export/import is the *next* thing to add but the recorder+replay pair alone already lets a user archive and replay a season.

### Add After Validation (v1.x)

Once the core loop (connect → cache → query → record/replay) is shipping and at least one downstream project has adopted it.

- [x] **D4, D5** — export state + log to JSON/JSONL; import back. Trivial extensions, but only valuable after a user has run a season's worth of recordings.
- [x] **A1 inverse — optional `to_pandas()` adapter** if a user actually needs it. Don't add until requested.

### Future Consideration (v2+)

- **Sibling libraries** for other series (WEC, IMSA) — only if there's an actual maintainer + community for them.
- **Persistent cache** (A2 inverse) — only if NLS ever introduces rate limits.
- **Schema migration tools** (A14 inverse) — only if NLS breaks the schema in a way the tolerant parser can't handle.
- **WebSocket subscription to filtered streams** (server-side filter) — would only matter if NLS added such an endpoint.
- **Eventual replays (clock-synchronized)** — replay as fast as recorded, or as fast as the consumer wants, or with synthetic time-skip. Most users will be fine with "as fast as your consumer can drain the queue", but a clock-locked mode is a natural follow-up.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| T1 Connect + handshake | HIGH | LOW | **P1** |
| T2 Per-channel subscribe | HIGH | LOW | **P1** |
| T3 Typed decoder | HIGH | MEDIUM | **P1** |
| T4 UnknownPID handling | HIGH | LOW | **P1** |
| T5 async message stream | HIGH | LOW | **P1** |
| T6 Reconnect with backoff | HIGH | LOW-MED | **P1** |
| T7 Exception hierarchy | MEDIUM | LOW | **P1** |
| T8 In-memory cache | HIGH | MEDIUM | **P1** |
| T9 Per-car lap drilldown | HIGH | LOW | **P1** |
| T10 async context manager | HIGH | LOW | **P1** |
| T11 Type hints | MEDIUM | LOW | **P1** |
| T12 CLI entry point | MEDIUM | LOW | **P2** |
| T13 Structured logging | MEDIUM | LOW | **P2** |
| D1 Record to JSONL | HIGH | LOW | **P1** |
| D2 Replay from JSONL | HIGH | LOW-MED | **P1** |
| D3 Filter the cache | HIGH | MEDIUM | **P1** |
| D4 Export state + log | MEDIUM | LOW | **P2** |
| D5 Import state + log | MEDIUM | LOW | **P2** |
| D6 Clear cache | MEDIUM | LOW | **P1** |
| D7 Race-control event stream | MEDIUM | LOW | **P1** |
| D8 Live + replay parity | HIGH | LOW | **P1** |
| D9 HA-friendly (constraint) | HIGH | — | **P1** (constraint, not work) |

**Priority key:**
- **P1** — must have for launch. Library is broken or pointless without it.
- **P2** — should have; add as soon as P1s are stable.
- **P3** — nice to have; future consideration (see MVP section).

**Total P1 features:** 17 (most of the table). P2: 4. P3: 0 in the table — defer to v2.

---

## Competitor Feature Analysis

The most directly relevant comparator is **FastF1** (theOehrly/FastF1, 5.2k★, MIT, Python). Other "timing client" libraries exist in scattered forms (iracing SDKs, WEC scrapers, hobby NLS bots in JS) but none is large enough or maintained enough to be a primary reference.

| Feature | FastF1 (theOehrly) | Generic iracing timing | Hobby NLS JS bots (GitHub gists) | Our approach |
|---------|-------------------|------------------------|----------------------------------|--------------|
| Connect to live timing | Yes (SignalR protocol, F1TV auth required) | Yes (proprietary TCP) | Yes (WS or fetch scrape) | Yes (WebSocket, no auth, async) |
| Parse to typed objects | Yes (Pydantic-ish + per-channel classes) | Varies | Mostly raw dicts | Yes (typed dataclasses) |
| pandas DataFrames as primary | **Yes** — primary data shape | Sometimes | No | **No** — typed objects; pandas optional |
| Record to file | Yes (`SignalRClient(filename=...)`, JSONL-ish raw) | Some | Some | Yes (JSONL, typed) |
| Replay from file | Yes (`LiveTimingData(*files)`) | Some | No | Yes (same `NLSClient` object) |
| Persistent file cache (pickle + sqlite) | **Yes** — elaborate | No | No | **No** — in-memory only |
| Per-data-type filter API | Yes (`Laps.pick_*`, `.pick_driver`, etc.) | Limited | No | Yes (over typed cache) |
| Export / Import state | No explicit export | No | No | **Yes** (differentiation) |
| Plotting (Matplotlib) | **Yes** — first-class | No | No | **No** (anti-feature for this project) |
| External REST API wrapper | **Yes** (Ergast/Jolpica) | No | No | **No** (no equivalent for NLS) |
| Telemetry (per-sample) | **Yes** (F1 only) | Limited | No | **No** (NLS does not publish) |
| Authentication | **Yes** (F1TV account required) | Yes (iracing account) | No | **No** (NLS feed is public) |
| Async-first | No (sync, with `livedata` recording workaround) | Varies | Varies | **Yes** (explicit PROJECT.md choice) |
| Home Assistant friendly | No | No | No | **Yes** (explicit PROJECT.md requirement) |
| Single object for live+replay | No (SignalRClient vs LiveTimingData) | No | No | **Yes** (the user's chosen design) |
| License | MIT | Varies (often GPL) | Varies (often no license) | **MIT** (PROJECT.md) |
| Multiple series | **F1 only** | iracing only | One series each | **NLS only** (explicit Out-of-Scope in PROJECT.md) |

**Summary:** Our approach is the **subset of FastF1's design that fits a single async, no-auth, public, single-series, no-pandas, no-plot library**, with three additions FastF1 does not have: (1) a single client object for live+replay, (2) explicit export/import, (3) HA-friendly packaging. The export/import combo is the only thing FastF1 does not have; it is a small but real differentiator for archival use.

---

## Open Questions for Roadmap

These came up during research and should be resolved at the **discussion** step of the first phase, not now.

1. **What is the consumer-facing object — `NLSClient` or `NLSSession`?** FastF1 calls it `Session` (a single race). Our user wants both live and replay behind one object. `NLSClient` is probably right (it's a *client* of the WS) — but worth a 1-line check.
2. **Is the cache per-client or per-channel?** The user lists "per-car lap history, sector times, race messages, qualifying, statistics" — these are all keyed by the same `(event_id, session)` but stored differently. A single `Cache` object composed of sub-caches is the FastF1 shape; a flat dict is the simplest shape. STACK.md / ARCHITECTURE.md should pin this.
3. **What does the "live stream" return type look like — `Message` (typed per-PID) or `RawMessage` (parsed dict) + helper accessors?** FastF1 returns a per-PID object. We should do the same — `Message` is the base, `ResultMessage` / `RaceMessage` / `LapMessage` / `QualifyingMessage` / `StatisticsMessage` / `TimeSyncMessage` / `UnknownMessage` are subclasses.
4. **Should `D1 record` work *while* a live client is connected, or is it a separate "headless recorder" mode?** PROJECT.md says the recorder and the live client share the API surface. Two reasonable answers: (a) one client, `.record(path)` is a method that opens a file and tees; (b) `NLSRecorder` is a separate object. Option (a) is what the user wants (single object). Worth confirming.
5. **Should the "filter" be a method (`client.cars(class_="AT")`) or a separate query object (`cache.query().class_("AT")`)?** Either is fine; FastF1 uses a method-on-DataFrame. For typed objects, a builder-pattern query object reads more naturally but is more code.

---

## Sources

- **FastF1** — `https://github.com/theOehrly/FastF1` (5.2k★, MIT, last release v3.8.3 Apr 2026) — primary reference; documented signal-R `LiveTimingClient`, `messages_from_raw`, `LiveTimingData`, `Session` (load with `livedata=`), `Cache` class, exception hierarchy, `Logging` API. **HIGH confidence.**
- **FastF1 docs** — `https://docs.fastf1.dev/` (specifically the Live Timing Client, Rate Limits and Caching, Session, Timing Data, Exceptions, and Data Reference pages) — direct quotations about live-client record + replay split, two-stage cache, exception tree. **HIGH confidence.**
- **PROJECT.md** (this project) — own reverse-engineering notes for the NLS bundle, channel shape (PIDs 0/3/4/7/501/9002), short-code keys, host (`livetiming.azurewebsites.net`), WS handshake, vendor reconnect wrapper, `/laps-data` returning HTML. **HIGH confidence (own work).**
- **WebSearch/Brave/Exa/Firecrawl** — *not available in this environment*. Competitive breadth beyond FastF1 is narrower than ideal. The other libraries (iracing SDKs, WEC scrapers, hobby NLS bots) are mentioned as known categories but not individually verified.
- **GrandPrix** (PyPI, 0.1.2, Apr 2025) — checked but very early-stage, no useful API reference.

---

## Validation of User's Stated Feature Set

The user said: "the user explicitly wants recording, replay, cache, filter, export/import. Validate that this is the right feature set vs. alternatives."

**Verdict: yes, the set is right. Specifically:**

| User's stated feature | Maps to | Validation |
|----------------------|---------|------------|
| Recording | D1 | Direct FastF1 analogue (`SignalRClient` with `filename=`). The "you can't develop against a feed that's only live on Saturdays" problem is real and well-known. |
| Replay | D2, D8 | Direct FastF1 analogue (`LiveTimingData`). The user's "single API surface for live and replay" refinement (D8) is *stronger* than FastF1's and is a real differentiator. |
| Cache | T8 (in-memory) — and **not** A2 (file cache) | In-memory is correct for a no-rate-limit feed. FastF1's file cache exists to protect against Ergast rate limits; NLS has no such thing. Skip the file cache. |
| Filter | D3 | The strongest differentiator vs FastF1's "scan the DataFrame" approach. For consumers that don't want pandas, a typed filter API is the right shape. |
| Export/Import | D4, D5 | **Adds something FastF1 does not have.** Small but real differentiator for archival/season-summary use cases. |

The set is correctly identified, the *shape* of the filter API is the main design decision to pin (query builder vs method chain vs method-on-cache), and the *absence* of a persistent file cache is a deliberate, validated choice — not an oversight.

---

*Feature research for: AIO NLS Livetiming API (Nürburgring Langstrecken-Serie async client library).*
*Researched: 2026-06-20.*
