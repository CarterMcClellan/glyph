#!/bin/zsh
set -euo pipefail

GLYPH_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$GLYPH_ROOT"

if [[ ! -d node_modules ]]; then
  npm install
fi

exec npm start
