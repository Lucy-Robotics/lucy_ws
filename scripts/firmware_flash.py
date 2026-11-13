#!/usr/bin/env python3
"""
Cross-platform firmware flash script.
Flashes RP2040 boards via USB with UF2 files.
"""
import argparse
import sys
from pathlib import Path

# Allow `python scripts/firmware_flash.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_log import enable_ansi
from firmware_log import get_logger

log = get_logger()

RP2040_PACKAGE = "lucy_embedded_firmware_rp2040"
UF2_DIR = (
    Path(__file__).resolve().parents[1]
    / "install"
    / RP2040_PACKAGE
    / "share"
    / RP2040_PACKAGE
    / "firmware"
)


def main():
    enable_ansi()
    parser = argparse.ArgumentParser(description="Flash Lucy firmware to RP2040 boards")
    parser.add_argument("--board", help="Specific board ID to flash (e.g., left_arm)")
    parser.add_argument("--no-verify", action="store_true", help="Skip Modbus verification after flash")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Lucy Firmware Flash Tool")
    log.info("=" * 60)
    log.info("")
    log.warning("Flash implementation coming in Phase 6.1")
    log.info("  For now, manually copy .uf2 files to RP2040 in BOOTSEL mode")
    log.info("")

    # Installed by colcon (pixi run build / firmware-build-rp2040), not read from cargo's target/.
    uf2_files = sorted(UF2_DIR.glob("*.uf2")) if UF2_DIR.is_dir() else []
    if uf2_files:
        log.info("Built firmware files:")
        for uf2 in uf2_files:
            log.info(f"  - {uf2}")
    else:
        log.warning(f"No .uf2 files in {UF2_DIR}. Run 'pixi run firmware-build-rp2040' first.")

    log.info("")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
