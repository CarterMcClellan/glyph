#!/usr/bin/env bash
set -euo pipefail

GLYPH_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GLYPH_ENV_FILE="${GLYPH_ENV_FILE:-$GLYPH_ROOT/.glyph/backend.env}"

if [[ -f "$GLYPH_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$GLYPH_ENV_FILE"
  set +a
fi

mkdir -p "${GLYPH_WORKSPACE:-$GLYPH_ROOT/.glyph/workspace}"
cd "$GLYPH_ROOT"

exec "${GLYPH_PYTHON:-python3}" -m glyph_harness.server \
  --host "${GLYPH_API_HOST:-127.0.0.1}" \
  --port "${GLYPH_API_PORT:-47831}" \
  --project-root "$GLYPH_ROOT" \
  --workspace "${GLYPH_WORKSPACE:-$GLYPH_ROOT/.glyph/workspace}"
