#!/usr/bin/env python3
"""
Cross-platform firmware flash script.
Flashes RP2040 boards via USB with UF2 files.
"""
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Flash Lucy firmware to RP2040 boards")
    parser.add_argument("--board", help="Specific board ID to flash (e.g., left_arm)")
    parser.add_argument("--no-verify", action="store_true", help="Skip Modbus verification after flash")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Lucy Firmware Flash Tool")
    print("=" * 60)
    print()
    print("⚠️  Flash implementation coming in Phase 6.1")
    print("   For now, manually copy .uf2 files to RP2040 in BOOTSEL mode")
    print()
    
    uf2_dir = Path("src/lucy_embedded_firmware/target/thumbv6m-none-eabi/release")
    if uf2_dir.exists():
        uf2_files = list(uf2_dir.glob("*.uf2"))
        if uf2_files:
            print("📁 Built firmware files:")
            for uf2 in uf2_files:
                print(f"   - {uf2}")
        else:
            print("⚠️  No .uf2 files found. Run 'pixi run firmware-build' first.")
    else:
        print("⚠️  Build directory not found. Run 'pixi run firmware-build' first.")
    
    print()
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
