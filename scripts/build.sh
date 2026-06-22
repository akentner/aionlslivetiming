#!/usr/bin/env bash
# scripts/build.sh
# One-shot sanity check: uv build + twine check on the produced artifacts.
# Per D-29 — Phase 4 closes when this exits 0; the actual PyPI upload is
# a separate manual event outside this workflow.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

echo "==> uv build"
uv build

echo
echo "==> uv run python -m twine check dist/*"
uv run python -m twine check dist/*

echo
echo "OK: build + twine check passed. Artifacts:"
ls -la dist/
