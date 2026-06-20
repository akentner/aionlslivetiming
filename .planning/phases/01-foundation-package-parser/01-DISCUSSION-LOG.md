# Phase 1: Foundation (Package + Parser) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 01-foundation-package-parser
**Areas discussed:** Model layer, Parser error & log policy, Fixtures & live-data capture, Message base class & dispatch surface

---

## Model layer

| Option | Description | Selected |
|--------|-------------|----------|
| stdlib @dataclass(frozen=True, slots=True) | Zero deps; `.raw` field for forward-compat | |
| pydantic BaseModel with extra='allow' | Built-in forward-compat, JSON schema, mypy plugin | |
| Hybrid — dataclass for events, pydantic for state | Cleanest split; leaves are pure stdlib, mutable layers get pydantic | ✓ |

**User's choice:** Hybrid — dataclass for events, pydantic for state.
**Notes:** pydantic earns its place on the mutable, validation-heavy side (state); events stay pure stdlib with a `.raw: Mapping[str, Any]` field. Aligns with both ARCHITECTURE.md (events as dataclasses) and STACK.md (pydantic for tolerant schema) without conflict.

---

## Parser error & log policy

| Option | Description | Selected |
|--------|-------------|----------|
| Tolerant — partial Message, .raw preserved, WARNING log | Never raises on server evolution; one WARNING per (event_pid, missing_field) | ✓ |
| Strict — raise ParseError on malformed payloads | Loud; violates "tolerant parsing" guidance in PROJECT.md | |
| Degrade — partial Message, ERROR log, no .raw | Compromise; loses forward-compat escape hatch | |

**User's choice:** Tolerant — partial Message, .raw preserved, WARNING log.
**Notes:** 8 dataclasses declare optional fields with `Optional[...]` (or `tuple[...]` defaulting to `()`) for every field the server is known to omit. Dedupe the WARNING logs in-process keyed on `(event_pid, missing_field)` to avoid log spam.

---

## Fixtures & live-data capture

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-craft minimal happy-path fixtures | ~10 fixtures from PROJECT.md notes; live capture deferred | |
| Live capture as blocker | Phase 1 stalls waiting for next race | |
| JSONL tee logger first, run during next race, then hand-craft | Proves transport path; hard data before parsing | ✓ |

**User's choice:** JSONL tee logger first, run during next race, then hand-craft from captured data.
**Notes:** Hard deadline 16:00 CEST on the gather day for live capture. If missed, fall back to hand-craft-only and add live-capture to Phase 3 as its first action. The early logger's line shape `{ts_recv_ms, raw}` is a strict subset of Phase 2's recorder schema `{ts_recv_ms, event_pid, raw, parsed}` — no migration needed later.

---

## Message base class & dispatch surface

| Option | Description | Selected |
|--------|-------------|----------|
| Flat @dataclass union, no base class, match/case dispatch | 8 independent classes; `event_pid: ClassVar[int]`; `Message = Union[...]` | ✓ |
| Message ABC with .event_pid ClassVar + is_unknown() helper | Explicit polymorphism, but couples siblings via a common ancestor | |
| Tagged union via Literal['initial_state', ...] discriminator | Most modern, but extra indirection in dispatcher | |

**User's choice:** Flat @dataclass union, no base class, match/case dispatch.
**Notes:** `type(msg).event_pid` for isinstance-callers. Public type alias `Message = Union[InitialStateMessage, TrackStateMessage, ...]`. Dispatcher in `parser/__init__.py` uses `match raw.get("eventPid"):`.

---

## the agent's Discretion

- Internal module naming inside `parser/` and `events/` (ARCHITECTURE.md lines 67-74 is the default).
- Exact `__repr__` of dataclass variants.
- In-process set keyed on `(event_pid, missing_field)` for WARNING log dedupe.
- `__version__` value (`"0.1.0"` matches RESEARCH.md).

---

## Deferred Ideas

None — discussion stayed within Phase 1 scope.

The following items are flagged in `research/SUMMARY.md` §Gaps and will be resolved at the discuss-phase of their owning phase:
- Filter API shape (Phase 2)
- `NLSClient` vs `NLSLivetimingClient` naming (Phase 4)
- Recorder-mode choice (method-on-client vs separate NLSRecorder) (Phase 4)
- Cache layout (flat vs composed sub-caches) (Phase 2)
- Public exception class names (Phase 4)
- `Source` enum naming (Phase 3)
- `LTS_NOT_FOUND` default policy (Phase 3)
