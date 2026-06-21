# Phase 4: Client + Distribution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-21
**Phase:** 04-client-distribution
**Areas discussed:** CLI surface & naming, NLSClient construction ergonomics, Documentation tooling, Worked examples scope

---

## CLI surface & naming

| Option | Description | Selected |
|--------|-------------|----------|
| Two short console scripts | Ship `nls-record` / `nls-replay` (DIST-05 literal). Deprecate `aionlslivetiming-capture` with one-release alias. | |
| Typer app with subcommands | One `aionlslivetiming` script with `record`/`replay` subcommands. Adds Typer dep. | |
| Keep current + add replay | Keep `aionlslivetiming-capture`, add `aionlslivetiming-replay`. Doesn't satisfy DIST-05. | |
| Module-name only | `python -m aionlslivetiming record ...` — no console scripts. Violates DIST-05. | |

**User's choice:** Two short console scripts (D-01)

### Old CLI fate

| Option | Description | Selected |
|--------|-------------|----------|
| Repurpose as `nls-record` | Move body to `cli/record.py`, delete old console script, keep `cli/jsonl_logger.py` shim with DeprecationWarning | |
| Hard cut to new name | Delete `cli/jsonl_logger.py` outright + remove old script entry | ✓ |
| Keep both indefinitely | Alias both names to the same body | |

**User's choice:** Hard cut to new name (D-02) — library never published, no external users to churn

### Replay CLI flags

| Option | Description | Selected |
|--------|-------------|----------|
| Full D-15 surface | `nls-replay <path>` with `--speed`, `--show-time-sync`, prints one-line `repr(msg)` to stdout | ✓ |
| Minimal passthrough | Just iterate, print only with `--verbose` | |
| Stats-only dump | Count messages per PID, no message output | |

**User's choice:** Full D-15 surface (D-03)

### Error handling

| Option | Description | Selected |
|--------|-------------|----------|
| Exit 0 with warning logs (default) + `--strict` exits 1 | Consistent with parser D-03 tolerance. `--strict` opt-in for CI. | ✓ |
| Exit 1 on any warning | Loud but contradicts parser philosophy | |
| Exit code = exception name | Precise signal, complex to remember | |

**User's choice:** Exit 0 with warning logs by default; `--strict` exits 1 (D-04)

### Additional `nls-replay` flag added in discussion

`--summary` flag for end-of-stream diagnostics (message count by PID, first/last timestamps, UnknownMessage events) — not in the original 4 questions; raised during discussion and accepted as D-05.

---

## NLSClient construction ergonomics

### Construction

| Option | Description | Selected |
|--------|-------------|----------|
| Direct constructor + transport-injection + `from_replay` class method | `NLSClient(event_id=...)` for live, `NLSClient.from_replay(path)` for replay, `transport=...` for power users | ✓ |
| Factory methods only | `NLSClient.live(...)`, `NLSClient.replay(...)` | |
| Transport-first composition | `NLSClient(transport=LiveTransport(...))` — uniform with Phase 3 | |

**User's choice:** Direct constructor + transport-injection (D-06, D-07)

### State ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Own RaceState, auto-apply, expose `state` | `client.state` is a `RaceState`; every Message applied before yielded | ✓ |
| Consumer applies manually | `messages()` yields raw Messages; no `client.state` | |
| Optional cache via kwarg | `state=RaceState(...)` opt-in | |

**User's choice:** Own RaceState, auto-apply, expose `state` (D-08)

### Iterator surface

| Option | Description | Selected |
|--------|-------------|----------|
| `messages()` + `time_sync()` + `lts_not_found()` separate iterators | Matches Phase 3 D-04 three-stream split | ✓ |
| One stream with tagged union | Single `messages()` yields Message OR TimeSyncMessage OR LTSNotFoundEvent | |
| Callback registration | Push model: `client.on_message(cb)` | |

**User's choice:** Three separate async iterators (D-10) — matches Phase 3 invariants

### Recording hook

| Option | Description | Selected |
|--------|-------------|----------|
| Optional `record_to=path` kwarg | NLSClient builds `RecordingTransport(LiveTransport(...), JsonlRecorder(path))` internally | ✓ |
| Separate CLI only | No client integration; manual composition | |
| Record-as-callback | `client.on_message(cb)` registers recorder | |

**User's choice:** Optional `record_to=path` kwarg (D-06 last bullet) — composition, not subclass (REC-03 invariant preserved)

---

## Documentation tooling

### API ref tool

| Option | Description | Selected |
|--------|-------------|----------|
| mkdocs + mkdocstrings | mkdocs-material theme; `mkdocs serve`/`build`; modern Python lib standard | ✓ |
| pdoc | Zero-config HTML; less customizable | |
| sphinx | Overkill for this size | |
| Defer (README-only) | Violates DIST-02 | |

**User's choice:** mkdocs + mkdocstrings (D-15)

### Docs structure

| Option | Description | Selected |
|--------|-------------|----------|
| Slim README + docs/ tree | README = install + 60s quickstart + license; docs/ = full walkthrough + examples + auto-API | ✓ |
| One big README | README is everything; docs/ only has API ref | |
| No docs/ — README is everything | Doesn't satisfy DIST-02 | |

**User's choice:** Slim README + docs/ tree (D-13, D-14)

### CHANGELOG format

| Option | Description | Selected |
|--------|-------------|----------|
| Keep a Changelog 1.1.0 + SemVer 2.0.0 | Standard format; v0.1.0 entry with Added/Removed/etc. sections | ✓ |
| Auto-generated from conventional commits | High process burden for alpha with one contributor | |
| GitHub Releases only | Violates DIST-03 | |

**User's choice:** Keep a Changelog format (D-17)

### CONTRIBUTING depth

| Option | Description | Selected |
|--------|-------------|----------|
| Light contributing guide | Dev setup, test/lint/typecheck commands, dataclass-vs-pydantic rule, how to add a Message variant | ✓ |
| Light + PR/issue templates | More polished but not needed for alpha | |
| Skip contributing guide | Violates DOC-05 | |

**User's choice:** Light contributing guide (D-18)

---

## Worked examples scope

### Example topics

| Option | Description | Selected |
|--------|-------------|----------|
| Live + replay + filter | Three core examples covering the value props; no HA | ✓ |
| Live + record + replay + filter (4 examples) | Covers full live → record → replay → analyze loop | |
| Live + replay + recording pipeline | Different mix; tells a story | |
| Live + replay + HA sensor | Conflicts with v2 HAI-01..03 being separate | |

**User's choice:** Live + replay + filter (D-20)

### Example format

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone runnable `.py` in `examples/` | Top-of-file docstring with `uv run python examples/<name>.py`; testable in CI with mocked transport | ✓ |
| Markdown-only code blocks | Not directly runnable | |
| Standalone `.py` + `docs/examples.md` index | Two places to keep in sync | |

**User's choice:** Standalone runnable .py in examples/ (D-21)

### Live example honesty (when no live race is running)

| Option | Description | Selected |
|--------|-------------|----------|
| Generic event_id placeholder | `event_id="YOUR_EVENT_ID"` with comment showing where to find a real one | ✓ |
| Replay transport by default | Doesn't showcase live prominently | |
| Include a recorded sample JSONL | Sample file is binary-ish, hard to review | |

**User's choice:** Generic event_id placeholder (D-20 first bullet)

### Final exception hierarchy decision (D-EXC deferred from Phase 3)

| Option | Description | Selected |
|--------|-------------|----------|
| Keep top-level + finalize names | `exceptions.py` stays at top level; finalize names; add `ParseError` and `LTSNotFoundError`; `LTSNotFoundEvent` (event) and `LTSNotFoundError` (exception) are deliberately distinct | ✓ |
| Move to subpackage + add ParseError | Changes import paths; bigger churn than v1 needs | |
| No changes from Phase 3 | Leaves D-EXC deferred item dangling in public API | |

**User's choice:** Keep top-level + finalize names (D-23, D-24, D-25)

---

## the agent's Discretion

Items the user delegated to the agent's judgment during discussion (all captured in CONTEXT.md §agent's Discretion):

- Internal layout of `cli/` (record.py / replay.py; no `__main__.py`)
- Exact `NLSClient.__repr__` shape
- Internal task-management inside `NLSClient.messages()` (delegate to transport's `__aiter__` vs own multiplexer)
- `examples/data/sample_event.jsonl` exact fixture contents
- README badge URLs (placeholders if no CI yet)
- README "Acknowledgements" wording
- `scripts/build.sh` thin wrapper vs README-documented command
- `mkdocs.yml` `nav:` section order

---

## Deferred Ideas

### From discussion

- **HA integration example** — explicitly out of scope per PROJECT.md and v2 HAI-01..03
- **Web UI / dashboard** — out of scope per PROJECT.md
- **`python -m aionlslivetiming` subcommand entry point** — not in DIST-05; would be a new requirement
- **GitHub Actions CI / release workflow** — no CI exists yet; first PyPI release is manual
- **`clock_offset` API expansion** beyond simple `.clock_offset_ms` property — deferred
- **PyPI trusted publishing setup** (GitHub Actions OIDC) — separate from "publish-ready" packaging
- **File rotation for JsonlRecorder** (Pitfall #12) — no user has hit the threshold yet
- **Telemetry / per-second car data** — not published by NLS livetiming
- **Multi-source clients** (v2 MULT-01..02) — explicitly deferred per REQUIREMENTS.md

### Out of scope for this phase

- Actual PyPI publishing
- HA integration package (v2)
- Persistence beyond JSON/JSONL (v2 PERS-01..02)
