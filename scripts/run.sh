#!/usr/bin/env bash
# Entry point for local development — starts Postgres, API, worker, and dashboard.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/dev.sh" "$@"
