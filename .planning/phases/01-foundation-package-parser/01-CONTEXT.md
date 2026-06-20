# Phase 1: Foundation (Package + Parser) - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning
**Deadline note:** A live-data capture step is sequenced into Phase 1 to run before parser work — see D-07.

<domain>
## Phase Boundary

Phase 1 delivers two things, and only these two:

1. **A packaged, installable Python project** — `pyproject.toml` with hatchling, HA-pinned dependency versions, `src/` layout, `py.typed` (PEP 561), `python_requires=">=3.12"`, zero `homeassistant.*` imports.
2. **Pure-function parsers** — eight typed `Message` dataclasses and a `parse(raw: dict) -> Message` dispatcher that decodes all known short-code server payloads (PIDs 0/3/4/7/501/9002 + time-sync) into typed objects. Zero I/O, zero async, zero transport. Hand-crafted fixtures prove the design without a live server.

**Explicitly out of scope** (later phases):
- Transport, state, filtering, recording, replay, client composition, HTTP, distribution/CLI/PyPI
- `homeassistant.*` integration code
- Any `await` on the parser hot path

</domain>

<decisions>
## Implementation Decisions

### Model layer — hybrid split
- **D-01:** `events/*` Message classes (the 8 typed dataclasses) are **stdlib `@dataclass(frozen=True, slots=True)`** — zero third-party deps on the leaf layer. Each carries `event_pid: ClassVar[int]` and `raw: Mapping[str, Any]` for forward-compat.
- **D-02:** `state/*` (Phase 2) uses **pydantic==2.13.4** with `model_config = ConfigDict(extra="allow", populate_by_name=True)`. Pydantic earns its place on the mutable, validation-heavy side; events stay pure stdlib.

### Parser error & log policy — tolerant
- **D-03:** `parse()` **never raises** on a known-PID / missing-field / malformed payload. It constructs a Message with the missing optional fields set to `None` (or a documented sentinel for tuple fields), preserves `.raw`, and logs a `WARNING` via `logging.getLogger("aionlslivetiming.parser")` once per `(event_pid, missing_field)` tuple. The 8 dataclasses declare optional fields with `Optional[...]` (or `tuple[...]` defaulting to `()`) for every field the server is known to omit.
- **D-04:** Unknown eventPid → `UnknownMessage(event_pid=<int>, raw=<dict>)` logged at WARNING. Library never crashes on server evolution. (Already-locked requirement: PARSE-03, pitfall #2/#9, anti-pattern #5.)
- **D-05:** Time-sync frames (`{"type": "time", "value": <ms>}`) branch **before** PID lookup and never enter the race-message stream. TimeSyncMessage is a separate variant on the same union. (Already-locked: pitfall #2.)

### Message base class & dispatch — flat union + match/case
- **D-06:** No base class, no inheritance. Eight independent `@dataclass(frozen=True, slots=True)` classes. Public type alias: `Message = Union[InitialStateMessage, TrackStateMessage, RaceMessage, PerCarLapsMessage, QualifyingMessage, StatisticsMessage, TimeSyncMessage, UnknownMessage]`. Dispatcher in `parser/__init__.py` uses `match raw.get("eventPid"):` (Python 3.12 structural matching). Each variant carries `event_pid: ClassVar[int]` so isinstance-callers use `type(msg).event_pid`.

### Fixtures & live-data capture — JSONL tee first, then parse
- **D-07:** **Before building the 8 parser functions**, ship a tiny logger-only CLI that connects to `wss://livetiming.azurewebsites.net/`, sends the handshake, and appends every raw WS frame to a JSONL file with the line shape `{ts_recv_ms, raw}`. No parsing, no typing — just the bytes. Run it against a live NLS session to capture a real JSONL (deadline noted: 16:00 CEST on gather day, otherwise fall back to the next live event). The captured JSONL is the **source of truth** for the hand-crafted fixture files.
- **D-08:** Eight hand-crafted happy-path fixtures (one per PID 0/3/4/7/501/9002 + one for time-sync) live in `tests/fixtures/messages/` as `pid_<n>_<scenario>.json` plus `time_sync.json`. Add `unknown_pid.json` and `pid_0_lts_not_found.json` for the negative paths. Each fixture is committed to the repo and the public contract for parser tests.
- **D-09:** Coverage gate from DIST-06 (≥80% on parser + state) is enforced by the captured-fixture suite. State coverage is a Phase 2 concern; Phase 1 closes the parser branch.

### Packaging & deps — HA-pinned, src-layout, py.typed
- **D-10:** `pyproject.toml` uses **hatchling** build backend, `src/` layout. Runtime deps pinned to match HA core: `pydantic==2.13.4` (only required by state/, Phase 2 — but listed now so the env is stable), `websockets>=15.0.1,<17`, `httpx>=0.28,<0.29`, `orjson>=3.11,<4` (optional, stdlib `json` fallback). Dev deps: `pytest>=9.0`, `pytest-asyncio>=1.4,<2` (auto mode), `pytest-cov>=7,<8`, `respx>=0.23`, `ruff>=0.15`, `mypy>=1.1,<2.2`. (Already-locked: STACK.md.)
- **D-11:** `python_requires=">=3.12"` (matches STACK.md rationale; HA consumer-friendly). `py.typed` marker shipped. Zero `homeassistant.*` imports — verified by `ruff`/`grep` in CI. (Already-locked: DIST-02, DIST-03, DIST-04, DIST-07.)

### Test infrastructure
- **D-12:** `pytest-asyncio` runs in `auto` mode for the JSONL logger CLI tests (the only async surface in Phase 1). Parser tests are pure sync — no event loop. The captured JSONL provides a `@pytest.mark.live`-free test suite for the parser layer.
- **D-13:** Coverage gate is `>=80%` on `aionlslivetiming/parser/` and `aionlslivetiming/events/` only for Phase 1. State coverage is a Phase 2 gate.

### the agent's Discretion
- Internal module naming inside `parser/` and `events/` (one-file-per-PID per ARCHITECTURE.md; planner can use the exact filenames in `.planning/research/ARCHITECTURE.md` lines 67-74 as the default).
- Exact `__repr__` of dataclass variants (sensible defaults, no user-facing impact).
- How to dedupe WARNING logs in D-03 (in-process set keyed on `(event_pid, missing_field)`; planner's call).
- `__version__` value (`"0.1.0"` matches RESEARCH.md; trivial to bump later).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent
- `.planning/PROJECT.md` — vision, requirements, reverse-engineering notes (server schema, channel IDs, handshake shape, `/laps-data` HTML behavior)
- `.planning/REQUIREMENTS.md` — PARSE-01..05, DIST-02, DIST-03, DIST-06, DIST-07 (Phase 1 scope), and the full v1 set for downstream awareness
- `.planning/ROADMAP.md` §Phase 1 — success criteria and scope anchor

### Stack & architecture (locked)
- `.planning/research/STACK.md` — exact dependency versions, HA pin rationale, library comparison (WebSocket / pydantic / httpx choice)
- `.planning/research/ARCHITECTURE.md` — 5-layer pipeline, package layout, Message pattern (frozen dataclass + raw field), parser dispatcher pattern, testability gradient
- `.planning/research/SUMMARY.md` §Key Findings, §Architecture Approach, §Pitfalls — exec summary the planner can read instead of the long-form docs
- `.planning/research/PITFALLS.md` — pitfall #2 (time-sync pollution), #4 (LTS_NOT_FOUND three-way semantics), #9 (schema drift → UnknownMessage), #15 (PyPI packaging)

### Server protocol (reverse-engineering notes)
- `.planning/PROJECT.md` §Context — host, channel PIDs 0/3/4/7/501/9002, payload keys (PID/VER/EXPORTID/SESSION/CUP/HEAT/HEATTYPE/TRACKNAME/STQ/BEST/TOD/RESULT/TRACKSTATE/TIMESTATE/ENDTIME/LTS_NOT_FOUND), handshake shape, `{type:"time"}` time-sync prelude

### External (HA core, for dep version verification only — no HA imports)
- `https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/package_constraints.txt` — authoritative source for `pydantic==2.13.4`, `httpx==0.28.1`, `websockets>=15.0.1`, `orjson==3.11.9`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — empty repo, greenfield project. No existing code, components, or utilities to reuse in Phase 1.

### Established Patterns
- The project will follow the patterns locked in `.planning/research/ARCHITECTURE.md` (5-layer pipeline, strict downward dependencies, `events/` and `parser/` are leaves) and `.planning/research/STACK.md` (HA-pinned deps, hatchling build). The planner does not have prior code to mirror — it should follow these docs as the style guide.

### Integration Points
- The captured JSONL (D-07) becomes the seed for the hand-crafted fixtures (D-08) and is the only "external" input the parser layer needs.
- Phase 2 (State + Filtering) consumes the 8 Message dataclasses via the public `Message` union type. Phase 1's `__init__.py` exports shape what Phase 2 can import.
- The JSONL line shape `{ts_recv_ms, raw}` (D-07) is the precursor to Phase 2's `recorder/jsonl.py` schema `{ts_recv_ms, event_pid, raw, parsed}` — keep the early logger's line shape a strict subset so no migration is needed later.

</code_context>

<specifics>
## Specific Ideas

- The "JSONL logger first, parse second" sequencing (D-07) is non-negotiable for Phase 1. The user wants a hard proof of the transport path against a real server before committing to fixture data. If 16:00 CEST is missed, fall back to a hand-craft-only Phase 1 and add the live-capture step to Phase 3 (Transport + Replay) as the first action there.
- The dataclass-for-events / pydantic-for-state split (D-01, D-02) is the cleanest separation. Planner should NOT mix the two — every Message in `events/` is stdlib dataclass, every model in `state/` is pydantic. Document the rule in `AGENTS.md` or a `CONTRIBUTING.md` stub.
- The 8 fixture filenames should follow the pattern already used in `ARCHITECTURE.md` line 109-118: `pid_<n>_<scenario>.json` for the 6 race messages, plus `time_sync.json` and `unknown_pid.json`. No novel naming.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope.

(Filter API shape, single-object naming `NLSClient` vs `NLSLivetimingClient`, recorder-mode choice, cache layout, exception class names, `Source` enum naming, and `LTS_NOT_FOUND` default policy are flagged in `research/SUMMARY.md` §Gaps and will be resolved at the discuss-phase of their owning phase — Phase 2 for the cache/filter items, Phase 3 for transport, Phase 4 for client/CLI.)

</deferred>

---
*Phase: 01-foundation-package-parser*
*Context gathered: 2026-06-20*
