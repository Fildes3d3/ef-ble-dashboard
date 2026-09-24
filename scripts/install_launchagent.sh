#!/usr/bin/env bash
# Keep the gateway running: start it at login, and restart it if it ever exits.
#
# It launches the .app rather than uvicorn directly, because macOS grants
# Bluetooth to the bundle, not to the Python binary (see the README). `open -W`
# waits for the app, so launchd's KeepAlive sees the app exiting, not `open`.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="$root_dir/tools/EcoFlow Gateway.app"
label="local.ecoflow.gateway"
plist="$HOME/Library/LaunchAgents/$label.plist"

[ -d "$app_dir" ] || { echo "Build the launcher first: bash scripts/make_launcher.sh"; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-W</string>
    <string>$app_dir</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardErrorPath</key><string>$root_dir/data/launchagent.log</string>
  <key>StandardOutPath</key><string>$root_dir/data/launchagent.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$plist"
echo "Installed $plist"
echo "The gateway now starts at login and restarts within 30s if it exits."
echo "Remove it with:  launchctl bootout gui/\$UID/$label && rm '$plist'"
