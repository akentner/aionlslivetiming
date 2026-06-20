#!/usr/bin/env bash
# Capture raw WebSocket frames from the NLS livetiming service to a JSONL
# file. Convenience wrapper around `uv run aionlslivetiming-capture` so
# you don't have to remember the long module path.
#
# Usage:
#   scripts/capture.sh <event_id> <output.jsonl> [--max-seconds N]
#
# Example:
#   scripts/capture.sh 20 /tmp/nls_event20.jsonl --max-seconds 30
#
# Requires uv on PATH (https://docs.astral.sh/uv/).

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <event_id> <output.jsonl> [--max-seconds N]" >&2
  exit 64
fi

exec uv run aionlslivetiming-capture "$@"