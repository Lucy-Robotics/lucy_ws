#!/usr/bin/env bash
# Install Lucy USB-serial udev rules (Pico CDC + Feetech host dongle).
#
# Usage:
#   ./scripts/setup_udev.sh
#   # or: pixi run setup-udev
#   # or: pixi run firmware-setup  (calls the same Python helper)
#
# On NixOS, imperative /etc/udev install cannot persist — the Python helper
# prints a host-specific configuration.nix snippet to copy/paste instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/firmware_usb_access.py" "$@"
