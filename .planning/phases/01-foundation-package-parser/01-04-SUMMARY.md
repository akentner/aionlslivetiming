---
phase: 01-foundation-package-parser
plan: 04
type: execute
status: complete
completed: 2026-06-20
---

# Phase 01 Plan 04: UAT gap closure — install command wording

## What changed

Documentation-only fix aligning 3 planning artifacts with the project's canonical install command (`uv sync --extra dev`, per `README.md` line 20).

3 files modified, 6 string-level edits:

| File | Edits |
|------|-------|
| `.planning/phases/01-foundation-package-parser/01-UAT.md` | Test 1 expected preamble; Test 6 `uv pip install -e ".[dev]"` → `uv sync --extra dev --reinstall`; Gaps section `reason` + `root_cause` rewritten as resolved; Gaps `missing` items suffixed with `— DONE` |
| `.planning/ROADMAP.md` | Phase 1 success criterion #1: `pip install -e .` + `pytest` → `uv sync --extra dev` + `uv run pytest` |
| `.planning/phases/01-foundation-package-parser/01-VERIFICATION.md` | Observable Truths row #1 preamble; DIST-03 evidence column |

## Verification evidence

```
$ grep -l 'uv sync --extra dev' .planning/phases/01-foundation-package-parser/01-UAT.md \
                                 .planning/ROADMAP.md \
                                 .planning/phases/01-foundation-package-parser/01-VERIFICATION.md
.planning/phases/01-foundation-package-parser/01-UAT.md
.planning/ROADMAP.md
.planning/phases/01-foundation-package-parser/01-VERIFICATION.md

$ grep 'pip install -e' <same 3 files>
(no matches — OK)

$ git diff --stat .planning/
 .planning/ROADMAP.md                                         |  2 +-
 .planning/phases/01-foundation-package-parser/01-UAT.md      | 12 ++++++------
 .../phases/01-foundation-package-parser/01-VERIFICATION.md   |  4 ++--
 3 files changed, 9 insertions(+), 9 deletions(-)

$ git diff --stat <SUMMARYs, 01-01-PLAN.md, PITFALLS.md>
(empty — historical files untouched)
```

## Untouched scope

Per the plan's scope discipline:

- `01-01-SUMMARY.md`, `01-02-SUMMARY.md`, `01-03-SUMMARY.md` — historical artifacts accurately documenting the `uv pip install -e ".[dev]"` form used at execution time.
- `.planning/research/PITFALLS.md` — PyPI-consumer-facing `pip install` examples are correct in their context.
- `.planning/phases/01-foundation-package-parser/01-01-PLAN.md` — historical plan file (out of scope per background note).

`README.md` was the source of truth and already used `uv sync --extra dev`; no change required.

## UAT re-test recommendation

Re-run `/gsd-verify-work` to confirm all 17 UAT tests now pass cleanly with the canonical install command. Test 1 + Test 6 should flip from `issue` / `pass`-but-outdated → `pass`. Tests 8-16 remain `skipped` (covered by existing parser unit tests, per user note).