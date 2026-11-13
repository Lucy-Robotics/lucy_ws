#!/usr/bin/env python3
"""
Run ``cargo test`` or ``cargo clean`` on each lucy_embedded_firmware package.

The firmware repo has no Cargo workspace: every firmware builds on its own, into its
own ``target/``. This walks the packages the former workspace covered.

    python scripts/firmware_cargo_each.py test|clean
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Allow `python scripts/firmware_cargo_each.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_cargo_env import configure_cargo_homes
from firmware_cargo_env import require_pixi_env
from firmware_log import enable_ansi
from firmware_log import get_logger

log = get_logger()

FIRMWARE_ROOT = Path(__file__).resolve().parents[1] / "src" / "lucy_embedded_firmware"
# Not compiling yet (see the TODO in firmwares/rp2040/build.rs).
SKIPPED_CRATES = {"builder"}
HOST_FIRMWARES = ["linux", "mcu_bridge"]
# arduino_mega stays out: its target/lucy holds the config pipeline's generated tables.
CLEAN_ONLY_FIRMWARES = ["rp2040"]


def packages(command: str) -> list[Path]:
    crates = sorted(
        p.parent
        for p in (FIRMWARE_ROOT / "crates").glob("*/Cargo.toml")
        if p.parent.name not in SKIPPED_CRATES
    )
    firmwares = HOST_FIRMWARES + (CLEAN_ONLY_FIRMWARES if command == "clean" else [])
    return crates + [FIRMWARE_ROOT / "firmwares" / name for name in firmwares]


def main(argv: list[str] | None = None) -> int:
    enable_ansi()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("test", "clean"):
        print("Usage: python scripts/firmware_cargo_each.py test|clean", file=sys.stderr)
        return 2
    command = args[0]

    configure_cargo_homes(require_pixi_env())
    for package in packages(command):
        log.info(f"cargo {command}: {package.relative_to(FIRMWARE_ROOT)}")
        code = subprocess.run(
            ["cargo", command, "--manifest-path", str(package / "Cargo.toml")], check=False
        ).returncode
        if code != 0:
            log.error(f"cargo {command} failed for {package.relative_to(FIRMWARE_ROOT)}")
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
