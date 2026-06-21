---
phase: 03-transport-replay
plan: 04
subsystem: transport/recorder
tags: [gap-closure, jsonl, recorder, runtime-toggle, async, REC-02]

# Dependency graph
requires:
  - phase: 03-transport-replay (plan 01)
    provides: JsonlRecorder (asyncio.Queue + dedicated writer task) and Transport Protocol
  - phase: 03-transport-replay (plan 03)
    provides: RecordingTransport composition wrapper that this plan extends with the set_enabled passthrough
provides:
  - JsonlRecorder runtime enable/disable: `is_enabled` property + async `set_enabled(bool)` method (REC-02)
  - `append()` silently drops messages when the recorder is disabled — no close, no raise, no partial-line writes; writer task keeps draining the queue
  - RecordingTransport passthrough: `is_enabled` + `set_enabled(bool)` delegate to the wrapped recorder
  - 4 new tests covering toggle-while-idle, toggle-while-burst, post-close safety, and the wrapper passthrough
  - Resolution of the REC-02 gap flagged in `03-VERIFICATION.md`
affects:
  - phase: 04-client-distribution (NLSClient can expose a public `recorder_enabled` flag that flips the wrapped RecordingTransport on/off mid-session)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Async mutator: set_enabled is `async` even though the body is a single attribute write — keeps a single mutator pattern across the surface and lets the wrapper do `await self._recorder.set_enabled(...)` cleanly"
    - "Gate at insert, not at write: the disable check is at the top of `append()` (queue insertion point), not inside the writer loop. This means the writer never has to know about the flag, and already-queued messages still drain while disabled"
    - "Passthrough by composition: RecordingTransport.set_enabled simply forwards to the inner recorder — no state duplication, single source of truth for the enabled flag"
    - "Symmetric with `close()`: `set_enabled(False)` does NOT close the writer; `close()` does NOT touch the flag. A consumer can disable, then re-enable, then close — the writer task has been alive the whole time"

key-files:
  created: []
  modified:
    - src/aionlslivetiming/transport/recorder.py — added `self._enabled: bool = True` to `__init__`; added `is_enabled` property + async `set_enabled(bool)` method; gated `append()` on the flag (after the closed check, before queue insert)
    - src/aionlslivetiming/transport/recorder_wrapper.py — added `is_enabled` property + async `set_enabled(bool)` passthrough on RecordingTransport
    - tests/test_jsonl_recorder.py — added `make_msg(pid=0)` helper (informational, always returns InitialStateMessage) + 3 new tests: `test_set_enabled_disables_writes`, `test_toggle_while_iterating_safe`, `test_set_enabled_after_close_raises_no`
    - tests/test_recording_transport.py — added `test_recording_transport_set_enabled_passthrough` that exercises the wrapper's disable→iterate→zero-writes path
    - .planning/phases/03-transport-replay/03-VERIFICATION.md — frontmatter `rec_02_resolution:` block + appended "REC-02: Resolved" section with commit hashes, new-test table, and re-verified-at-21-of-21 summary
    - .planning/REQUIREMENTS.md — REC-02 line now annotated "runtime toggle landed in Plan 03-04"
    - .planning/ROADMAP.md — Phase 3 marked `[x]` Complete; progress row updated to 4/4

key-decisions:
  - "Async set_enabled, not sync: the plan's pseudo-code showed both `rec.set_enabled(False)` (sync, in the recorder section) and `await self._recorder.set_enabled(enabled)` (async, in the wrapper section). Picked async to match the wrapper's calling convention and to keep a single mutator pattern. The test calls `await rec.set_enabled(...)` everywhere; flag is observable immediately"
  - "Gate at the queue-insert point, not the writer loop: keeps the writer loop unchanged and the contract is 'future appends are dropped', matching the must-have 'Disabling does not drop messages already queued'"
  - "No new exception, no warning log per call: `set_enabled` is silent (only INFO at the recorder level, matching the existing logging style) and `append()` while disabled is a no-op. This is the right call for a power-user toggle — log noise on every dropped message would defeat the purpose"
  - "RecordingTransport.set_enabled does NOT touch the inner transport: only the on-disk recording pauses. The inner stream still flows to the consumer, matching the must-have 'Toggle-during-iteration is safe — the live message stream is not interrupted'"

patterns-established:
  - "Pattern: async flag-mutator on a public class — `set_X(bool)` is async even when the body is one assignment, so all mutator calls in the API follow the same await-shape"
  - "Pattern: toggle at the top of `append()` (the queue-insert point) for a 'gate at the source' design — simpler than gating the writer and lets the writer stay simple"
  - "Pattern: passthrough on a composition wrapper mirrors the inner API — `RecordingTransport` exposes `is_enabled` / `set_enabled` with the same signatures as `JsonlRecorder`"
  - "Pattern: 'disabled' is a soft state, 'closed' is a hard state — `close()` cancels the writer task; `set_enabled(False)` leaves it running. Two distinct lifecycle methods, two distinct meanings"

# Metrics
duration: ~10 min
completed: 2026-06-21
---

# Phase 3 Plan 4: REC-02 Gap Closure Summary

**One-liner:** JsonlRecorder + RecordingTransport gain runtime enable/disable via async `set_enabled(bool)` + `is_enabled` property; four new tests close the REC-02 gap and bring Phase 3 to 21/21 satisfied requirements.

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add `set_enabled` to `JsonlRecorder` + tests | `7d6bacd` | `src/aionlslivetiming/transport/recorder.py`, `tests/test_jsonl_recorder.py` |
| 2 | Add `set_enabled` passthrough to `RecordingTransport` + test | `84b1b6c` | `src/aionlslivetiming/transport/recorder_wrapper.py`, `tests/test_recording_transport.py` |
| 3 | Verify + close out (this task) | (below) | `.planning/phases/03-transport-replay/03-VERIFICATION.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `STATE.md`, this file |

## Deviations from Plan

**1. `set_enabled` is async, not sync (Rule 2 — auto-add missing critical functionality)**

- **Found during:** Task 1, while writing the first test
- **Issue:** The plan's pseudo-code was internally inconsistent: the recorder section shows `rec.set_enabled(False)` (sync, no `await`); the wrapper section shows `await self._recorder.set_enabled(enabled)` (async). The first test as literally written in the plan would have produced a `RuntimeWarning: coroutine 'JsonlRecorder.set_enabled' was never awaited` because the recorder method is `async` (so the wrapper's `await` works).
- **Fix:** Made the recorder's `set_enabled` `async` to match the wrapper's calling convention. This is the design that's load-bearing — without it, the wrapper would have to call `self._recorder._enabled = enabled` directly (leaky), or `asyncio.run(self._recorder.set_enabled(enabled))` (sync context), neither of which is right. Async throughout keeps the surface uniform.
- **Files modified:** `src/aionlslivetiming/transport/recorder.py`, `tests/test_jsonl_recorder.py` (test now uses `await rec.set_enabled(...)`)
- **Commit:** `7d6bacd`

**2. Test docstring shortened (Rule 3 — auto-fix blocking issue)**

- **Found during:** Task 1, `ruff check` after the first commit
- **Issue:** `test_toggle_while_iterating_safe`'s docstring was 102 chars; ruff E501 caps at 100. Pure formatting, no semantic change.
- **Fix:** Shortened the docstring to 99 chars.
- **Files modified:** `tests/test_jsonl_recorder.py`
- **Commit:** `7d6bacd` (folded into the same commit; no new commit for a docstring tweak)

**No other deviations.** Plan executed as written for everything else.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/ -q` | **261 passed in 20.21s** (was 257 — 4 new) |
| Coverage gate (>=80%) | **95.29%** (gate met; 80% required) |
| `uv run ruff check src/ tests/` | **All checks passed!** |
| `uv run mypy --strict` on changed `src/` files | **0 new errors** (2 pre-existing `orjson` `unused-ignore` documented in 03-02 SUMMARY remain) |
| `03-VERIFICATION.md` has "REC-02: Resolved" section | Yes, with both commit hashes and a 4-row test table |
| `REQUIREMENTS.md` REC-02 row updated | Yes, annotated "runtime toggle landed in Plan 03-04" |
| `ROADMAP.md` Phase 3 marked `[x]` | Yes (line 11 + progress row) |
| `RecordingTransport.set_enabled` delegates to `self._recorder.set_enabled` (key-link check) | Yes, verified by `test_recording_transport_set_enabled_passthrough` |

## New Tests

| Test | What it proves |
|------|----------------|
| `test_set_enabled_disables_writes` | `set_enabled(False)` then `append()` writes nothing; `set_enabled(True)` resumes; only the post-re-enable message is persisted |
| `test_toggle_while_iterating_safe` | 5 pre-toggle appends + 5 disabled-period appends (dropped) + 1 post-re-enable = 6 lines on disk; writer task survived the disable period |
| `test_set_enabled_after_close_raises_no` | Calling `set_enabled(False)` after `close()` is a safe no-op; flag is just stored |
| `test_recording_transport_set_enabled_passthrough` | `RecordingTransport.set_enabled(False)` produces **0** on-disk lines while still yielding all messages to the consumer; `is_enabled` reflects the inner recorder |

## Self-Check: PASSED

- `JsonlRecorder.set_enabled` and `is_enabled` exposed — ✓ (recorder.py lines 90-105)
- `RecordingTransport.set_enabled` and `is_enabled` exposed — ✓ (recorder_wrapper.py lines 71-83)
- 4 new tests pass — ✓ (3 on `JsonlRecorder`, 1 on `RecordingTransport`)
- 95% coverage preserved — ✓ (95.29%, gated write path exercised by `test_set_enabled_disables_writes`)
- mypy --strict + ruff clean on changed files — ✓ (0 new errors; 2 pre-existing `orjson` `unused-ignore` out of scope)
- `03-VERIFICATION.md` has a "REC-02: Resolved" section with the commit hash — ✓ (`7d6bacd`, `84b1b6c`)
- `ROADMAP §Phase 3` marked `[x]` Complete — ✓
