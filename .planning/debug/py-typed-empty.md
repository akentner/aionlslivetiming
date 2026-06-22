---
status: resolved
trigger: "src/aionlslivetiming/py.typed ist vorhanden, aber leer"
created: 2026-06-20T18:10:00Z
updated: 2026-06-20T18:10:00Z
---

## Current Focus

hypothesis: UAT #2 reported the py.typed file as "empty (0 bytes)" — this is NOT a bug, it's the canonical PEP 561 form.
test: Verified file size is 0 bytes; verified test_smoke.py explicitly asserts `marker.read_text() == ""`; verified pyproject.toml force-includes the file; verified PEP 561 spec.
expecting: NOT a bug — the file is correct, the test asserts emptiness, the UAT reporter misinterpreted the empty file as a defect.
next_action: Return structured diagnosis explaining PEP 561 + the explicit test assertion.

## Symptoms

expected: py.typed should be a valid PEP 561 marker
actual: File exists but is empty (0 bytes)
errors: none
reproduction: `ls -la src/aionlslivetiming/py.typed` → `0 bytes`
started: Discovered during UAT session 2026-06-20

## Eliminated

- hypothesis: py.typed should contain content (e.g. a version string or marker text)
  evidence: PEP 561 spec says: "Package maintainers who wish to support type checking of their code MUST add a marker file named py.typed to their package". The spec describes the file purely as a *marker* — existence is the signal. The only documented content variation is the optional `partial\n` for partial stub packages (PEP 561 §"Partial Stub Packages"), which is for `-stubs` packages only, not runtime packages shipping inline types.
  timestamp: 2026-06-20T18:10:00Z

- hypothesis: py.typed was accidentally truncated or the wrong file was committed
  evidence: File is exactly 0 bytes, the canonical size. test_smoke.py line 66 explicitly asserts: `assert marker.read_text(encoding="utf-8") == "", "py.typed must be empty"`. The emptiness is *required* by the project's own test suite.
  timestamp: 2026-06-20T18:10:00Z

- hypothesis: hatchling force-include is broken and dropping the file
  evidence: pyproject.toml line 60-61 has `[tool.hatch.build.targets.wheel.force-include] "src/aionlslivetiming/py.typed" = "aionlslivetiming/py.typed"`. Verification log (01-VERIFICATION.md line 21): `src marker is 0 bytes; [tool.hatch.build.targets.wheel.force-include] configured`. The test `test_py_typed_present` in test_smoke.py would fail if the marker didn't ship — and it passes.
  timestamp: 2026-06-20T18:10:00Z

## Evidence

- timestamp: 2026-06-20T18:10:00Z
  checked: src/aionlslivetiming/py.typed file size
  found: `stat` reports `size=0 bytes`; `wc -c` reports `0`; `read` tool reports "End of file - total 0 lines"
  implication: The file is exactly the canonical PEP 561 empty marker.

- timestamp: 2026-06-20T18:10:00Z
  checked: tests/test_smoke.py test_py_typed_present
  found: Test asserts (lines 60-66): `marker.exists()` AND `marker.read_text(encoding="utf-8") == ""` with message "py.typed must be empty". The test *requires* the file to be empty — if it contained any content, the test would fail.
  implication: Empty is the correct, tested, intended state.

- timestamp: 2026-06-20T18:10:00Z
  checked: pyproject.toml
  found: Lines 60-61: `[tool.hatch.build.targets.wheel.force-include]` with `"src/aionlslivetiming/py.typed" = "aionlslivetiming/py.typed"`. The 0-byte file is force-included into the wheel verbatim.
  implication: The empty marker ships in the installed package. PEP 561's "type checker finds py.typed in the package" condition is satisfied.

- timestamp: 2026-06-20T18:10:00Z
  checked: PEP 561 spec at https://peps.python.org/pep-0561/
  found: "Package maintainers who wish to support type checking of their code MUST add a marker file named py.typed to their package supporting typing." The spec never requires the file to contain any particular content. The only content variant in the spec is `partial\n` inside `py.typed` for *partial stub-only packages* (`<pkg>-stubs`), not for runtime packages with inline types.
  implication: A 0-byte py.typed in a runtime package with inline type hints is the canonical, spec-compliant PEP 561 marker.

- timestamp: 2026-06-20T18:10:00Z
  checked: 01-VERIFICATION.md (phase verification log)
  found: Line 21: "src marker is 0 bytes; [tool.hatch.build.targets.wheel.force-include] configured" — marked ✓ VERIFIED. Line 37: "0-byte marker file, force-included in wheel — ✓ VERIFIED". The empty py.typed was the verified, intended state.
  implication: The UAT reporter saw a 0-byte file, didn't know PEP 561 markers are conventionally empty, and flagged it as a defect.

## Resolution

root_cause: NOT A BUG. The 0-byte `src/aionlslivetiming/py.typed` is the canonical PEP 561 marker. PEP 561 ("Distributing and Packaging Type Information") requires the marker file to *exist* in the package; it does not require the file to contain any content. The project's own test (`tests/test_smoke.py::test_py_typed_present` line 66) explicitly asserts `marker.read_text(encoding="utf-8") == ""` with the message "py.typed must be empty". The file is force-included into the wheel via `[tool.hatch.build.targets.wheel.force-include]` in pyproject.toml, so it ships in the installed package. The UAT reporter (the user) likely expected to see content (e.g., a version string or "inline types" marker text) and interpreted the emptiness as a defect, but emptiness is the spec-compliant form for a runtime package with inline type annotations.
fix: None — no change required.
verification: (1) File is 0 bytes ✓ (2) `test_py_typed_present` passes (asserts file exists AND is empty) ✓ (3) pyproject.toml force-includes the marker ✓ (4) 01-VERIFICATION.md marked DIST-02 as ✓ VERIFIED ✓ (5) PEP 561 spec explicitly says py.typed is a marker file with no required content ✓
files_changed: []
