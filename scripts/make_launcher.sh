#!/usr/bin/env bash
# Build a small .app that launches the gateway.
#
# macOS refuses Bluetooth to any process whose responsible app has no
# NSBluetoothAlwaysUsageDescription in its Info.plist, and kills it with SIGABRT
# the moment it touches CoreBluetooth. Neither Homebrew's python nor Terminal.app
# carries that key, so `uvicorn` started from a shell always dies. Launching the
# server from this bundle instead makes the bundle the responsible app, and the
# uvicorn process it spawns inherits that grant.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="$root_dir/tools/EcoFlow Gateway.app"
port="${ECOFLOW_PORT:-8080}"

rm -rf "$app_dir"
mkdir -p "$app_dir/Contents/MacOS"

cat > "$app_dir/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIdentifier</key><string>local.ecoflow.gateway</string>
  <key>CFBundleName</key><string>EcoFlow Gateway</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSBackgroundOnly</key><true/>
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Reads DELTA 2 battery telemetry over Bluetooth on this machine.</string>
</dict>
</plist>
PLIST

cat > "$app_dir/Contents/MacOS/run" <<RUNNER
#!/bin/bash
root_dir="$root_dir"
port="$port"
log_file="\$root_dir/data/gateway.log"
mkdir -p "\$root_dir/data"

# Redirect before anything else, so a bad .env is visible in the log rather than
# vanishing into the launchd void.
exec >>"\$log_file" 2>&1
echo "=== gateway start \$(date) on port \$port ==="

# app/main.py reads .env itself, so nothing needs sourcing here.

exec "\$root_dir/.venv/bin/uvicorn" app.main:app --app-dir "\$root_dir" --host 0.0.0.0 --port "\$port"
RUNNER

chmod +x "$app_dir/Contents/MacOS/run"
codesign --force --sign - "$app_dir"

# ---------------------------------------------------------------------------
# The clickable one. The gateway above is a background service with no window,
# so double-clicking it looks like nothing happened. This app is what a person
# actually opens: it makes sure the service is up, then shows the dashboard.
dash_dir="$root_dir/tools/EcoFlow Dashboard.app"
rm -rf "$dash_dir"
mkdir -p "$dash_dir/Contents/MacOS"

cat > "$dash_dir/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIdentifier</key><string>local.ecoflow.dashboard</string>
  <key>CFBundleName</key><string>EcoFlow Dashboard</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
</dict>
</plist>
PLIST

cat > "$dash_dir/Contents/MacOS/run" <<RUNNER
#!/bin/bash
root_dir="$root_dir"
url="http://localhost:$port"

up() { curl -sS -m 2 "\$url/health" >/dev/null 2>&1; }

if ! up; then
  # -g keeps the service in the background; it has no window to show anyway.
  open -g "\$root_dir/tools/EcoFlow Gateway.app"
  for _ in \$(seq 1 40); do
    sleep 1
    up && break
  done
fi

if up; then
  open "\$url"
else
  osascript -e 'display notification "The gateway did not come up. See data/gateway.log." with title "EcoFlow Dashboard"'
  open -a Console "\$root_dir/data/gateway.log" 2>/dev/null || true
fi
RUNNER

chmod +x "$dash_dir/Contents/MacOS/run"
codesign --force --sign - "$dash_dir"

echo "Built: $dash_dir"
echo "Built: $app_dir"
echo "Double-click 'EcoFlow Dashboard' to open the dashboard (it starts the service if needed)."
echo "Logs:           $root_dir/data/gateway.log"
