#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Realtime limits only apply on Linux. Current OS: $(uname -s)"
  exit 0
fi

USER_NAME="${SUDO_USER:-$(id -un)}"
TARGET="/etc/security/limits.d/99-lucy-realtime.conf"

echo "Allowing ${USER_NAME} to run the control loop with realtime priority (requires sudo)..."
printf '%s - rtprio 70\n%s - memlock unlimited\n' "$USER_NAME" "$USER_NAME" \
  | sudo tee "$TARGET" >/dev/null
sudo chmod 0644 "$TARGET"
echo "  wrote ${TARGET}"
echo "Log out and back in, then check: ulimit -r  (expects 70)"
