#!/usr/bin/env bash
# Install Lucy USB-serial udev rules (Pico CDC + Feetech host dongle).
#
# Usage:
#   ./scripts/setup_udev.sh
#   # or: pixi run setup-udev
#   # or: pixi run firmware-setup  (calls the same install)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="${WORKSPACE_ROOT}/config/udev"
TARGET_DIR="/etc/udev/rules.d"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "udev rules are only applicable on Linux. Current OS: $(uname -s)"
  exit 0
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Error: udev rules directory not found at $SOURCE_DIR" >&2
  exit 1
fi

shopt -s nullglob
rules=("${SOURCE_DIR}"/*.rules)
if [[ ${#rules[@]} -eq 0 ]]; then
  echo "Error: no *.rules under $SOURCE_DIR" >&2
  exit 1
fi

echo "Installing Lucy USB-serial udev rules to $TARGET_DIR (requires sudo)..."
for src in "${rules[@]}"; do
  name="$(basename "$src")"
  sudo install -m 0644 "$src" "${TARGET_DIR}/${name}"
  echo "  installed ${name}"
done

# Drop the old RP2040-only filename if present (superseded by 99-lucy-usb-serial.rules).
if [[ -f "${TARGET_DIR}/99-lucy-rp2040.rules" ]]; then
  sudo rm -f "${TARGET_DIR}/99-lucy-rp2040.rules"
  echo "  removed obsolete 99-lucy-rp2040.rules"
fi

if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=tty
fi

echo "Done. Replug USB boards if they were already connected, or run firmware-setup again for a temporary chmod."
