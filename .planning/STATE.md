---
gsd_state_version: 1.0
milestone: v0.1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-01-PLAN.md
last_updated: "2026-06-20T17:32:44.338Z"
last_activity: 2026-06-20
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 7
  completed_plans: 5
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-20)

**Core value:** Downstream Python projects can subscribe to a running NLS race and get typed, filtered, cached race data — live or replayed from a log — without ever touching the Azure WebSocket or the cryptic short-code JSON the server actually emits.
**Current focus:** Phase 02 — state-filtering

## Current Position

Phase: 02 (state-filtering) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-06-20

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | TBD | TBD | — |
| 2. State + Filtering | TBD | TBD | — |
| 3. Transport + Replay | TBD | TBD | — |
| 4. Client + Distribution | TBD | TBD | — |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-foundation-package-parser P01 | 824s | 3 tasks | 16 files |
| Phase 01 P02 | 6 | 2 tasks | 23 files |
| Phase 01-foundation-package-parser P03 | 7min | 2 tasks | 24 files |
| Phase 02-state-filtering P01 | 360 | 1 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap structure: 4 phases (coarse granularity) collapsing the 10-step ARCHITECTURE.md build order into Foundation → State → Transport → Client+Distribution
- Phase 1 owns DIST-02/03/06/07 (packaging + dep pins + coverage gates) alongside PARSE-* because the package skeleton and the parser share the same src-layout scaffolding
- Phase 3 owns all of CONN + STREAM + REC + HTTP together — the Transport Protocol and its three implementations (Live / Replay / Recording wrapper) form one inseparable design unit, and splitting them would split the live-vs-replay parity guarantee
- [Phase 01-foundation-package-parser]: Hatchling build backend with src-layout; py.typed forced into wheel via hatch force-include (PEP 561)
- [Phase 01-foundation-package-parser]: orjson is an optional extra, not a hard runtime dep — stdlib json works as fallback (D-10)
- [Phase 01-foundation-package-parser]: JSONL line shape {ts_recv_ms, raw} is a strict subset of Phase 2 schema {ts_recv_ms, event_pid, raw, parsed} — no migration needed
- [Phase 01-foundation-package-parser]: Events layer is stdlib-only (@dataclass frozen+slots), no pydantic — D-01 dataclass-for-events / pydantic-for-state split is now enforced by the public surface
- [Phase 01-foundation-package-parser]: TimeSyncMessage.event_pid = -1 sentinel so the parser dispatcher routes by type-discriminator instead of needing a separate code path
- [Phase 01-foundation-package-parser]: 11 hand-crafted fixtures at tests/fixtures/messages/ are the D-08 public test contract — Plan 03 parser tests will load each fixture and assert the parsed Message shape
- [Phase 01-foundation-package-parser]: match/case over eventPid in the public parse() dispatcher — structural pattern matching reads as an exhaustive dispatch table; type-discriminated time-sync branch matched BEFORE eventPid lookup (D-05)
- [Phase 01-foundation-package-parser]: Single module-level _warned: set[tuple[int, str]] in parser/_helpers.py — shared dedupe set across all 8 per-PID parsers + dispatcher (D-03); autouse reset_warned() fixture in conftest.py for test independence
- [Phase 01-foundation-package-parser]: Coverage addopts use dotted module names (aionlslivetiming.parser) rather than the old forward-slash form — the slashed form silently produced 0% because coverage could not discover the packages as namespaces
- [Phase 02-state-filtering]: CarState is NOT frozen (sector_bests mutated in-place); LapRecord and TrackState ARE frozen (last-write-wins via key)
- [Phase 02-state-filtering]: RaceState.cars / stats_best_sectors return defensive dict copies; messages/qualifying are immutable tuples (no copy needed)
- [Phase 02-state-filtering]: Freshness defaults to RESYNCING (not FRESH) so a fresh RaceState() is honest about being empty; transitions to FRESH on first apply()
- [Phase 02-state-filtering]: Per-type idempotency strategies: PID 0 = full cars dict reset; PID 4 = replace TrackState instance; PID 3 = dedupe on (text, category, starting_no, session); PID 7 = keyed by (session, starting_no, lap_no) last-write-wins; PID 501 = replace results tuple; PID 9002 = keep min per (starting_no, sector)

### Pending Todos

None yet.

### Blockers/Concerns

- (Phase 1) Filter API shape — method-on-cache vs. builder-pattern query object — is an open design decision flagged in research/SUMMARY.md. Resolve via `/gsd-discuss-phase` before Phase 2 planning.
- (Phase 3) Azure App Service idle timeout, exact `websockets` library `ping_interval`/`close_timeout` tuning, and `LTS_NOT_FOUND` three-state policy all need a `/gsd-research-phase` spike before WebSocket implementation. Capture a real JSONL during a live test session before declaring Phase 3 done.

## Session Continuity

Last session: 2026-06-20T17:32:44.334Z
Stopped at: Completed 02-01-PLAN.md
Resume file: None
