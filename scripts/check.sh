#!/usr/bin/env bash
# Everything that guards the code, in one command.
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

# node:test needs Node 18+. Prefer whatever is on PATH; fall back to the newest
# nvm-managed copy, because a system node is often too old.
node_bin="$(command -v node || true)"
node_major() { "$1" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }
if [ -z "$node_bin" ] || [ "$(node_major "$node_bin")" -lt 18 ]; then
  newest="$(ls -d "$HOME"/.nvm/versions/node/v* 2>/dev/null | sort -V | tail -1)"
  [ -n "$newest" ] && [ -x "$newest/bin/node" ] && node_bin="$newest/bin/node"
fi
if [ -z "$node_bin" ] || [ "$(node_major "$node_bin")" -lt 18 ]; then
  echo "check.sh: Node 18+ is required for the JS tests; none found" >&2
  exit 1
fi

echo "== ruff =="
.venv/bin/ruff check .
echo "== pytest =="
.venv/bin/python -m pytest -q
echo "== node --test =="
"$node_bin" --test "tests/js/*.test.js" | tail -5
