#!/usr/bin/env bash
# scripts/check_no_ha_imports.sh
# CI guard: fail if any homeassistant.* import statement appears in src/ or tests/.
# Per Pitfall #14 + DIST-04 + D-30 — the core package must remain HA-free.
#
# Only matches actual Python import statements (`import homeassistant` or
# `from homeassistant ... import`); docstrings, comments, and identifier
# mentions (e.g. test names like `test_no_homeassistant_imports`) are
# intentionally ignored to avoid false positives.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

# Match lines that start (after optional whitespace) with `import homeassistant`
# or `from homeassistant(.*) import`. Case-sensitive per Python module naming.
PATTERN='^\s*(import[[:space:]]+homeassistant\b|from[[:space:]]+homeassistant(\.\w+)?[[:space:]]+import\b)'

matches="$(grep -rEn "${PATTERN}" src/ tests/ 2>/dev/null | grep -v __pycache__ || true)"

if [[ -n "${matches}" ]]; then
    echo "ERROR: homeassistant.* import statements detected in src/ or tests/" >&2
    echo "${matches}" >&2
    echo >&2
    echo "The aionlslivetiming core package must not import from homeassistant.*" >&2
    echo "(HA integration is a separate concern — see PROJECT.md and v2 requirements HAI-01..03)" >&2
    exit 1
fi

echo "OK: zero homeassistant.* import statements in src/ or tests/"