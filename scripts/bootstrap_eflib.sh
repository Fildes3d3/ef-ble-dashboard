#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="$root_dir/vendor/ha-ef-ble"

if [[ -d "$target_dir/.git" ]]; then
  git -C "$target_dir" pull --ff-only
else
  mkdir -p "$(dirname "$target_dir")"
  git clone --depth 1 https://github.com/rabits/ha-ef-ble.git "$target_dir"
fi

echo "EcoFlow BLE protocol source is ready at $target_dir"
