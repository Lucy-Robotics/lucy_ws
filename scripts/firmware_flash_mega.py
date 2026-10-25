#!/usr/bin/env python3
"""
Build and flash the Arduino Mega firmware for one board of the robot hardware YAML.

    pixi run firmware-flash-mega mega_arms

The board's ``compile_definition`` picks the cargo feature and its ``serial_id`` (the
Mega's USB serial number) picks the port, so several Megas can stay plugged in.
Needs ``avr-gcc`` and ``avrdude`` on the host (not on conda-forge).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from serial.tools import list_ports

# Allow `python scripts/firmware_flash_mega.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_cargo_env import configure_cargo_homes
from firmware_cargo_env import require_pixi_env
from firmware_log import enable_ansi
from firmware_log import get_logger

log = get_logger()

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
MEGA_CRATE = WORKSPACE_ROOT / "src" / "lucy_embedded_firmware" / "firmwares" / "arduino_mega"
MEGA_ELF = MEGA_CRATE / "target" / "avr-none" / "release" / "lucy-embedded-firmware-arduino-mega.elf"
# Must match firmwares/mcu_bridge and config/udev.
MEGA_VID, MEGA_PID = 0x2341, 0x0042


def load_board(robot: str, board_id: str) -> dict:
    path = WORKSPACE_ROOT / "src" / robot / "config" / "hardware" / "active.yaml"
    boards = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("boards") or {}
    board = boards.get(board_id)
    if board is None:
        megas = [b for b, d in boards.items() if d.get("board_class") == "i2c_pwm_only"]
        raise SystemExit(f"{board_id!r} is not a board of {path}; Mega boards: {', '.join(megas) or 'none'}")
    if board.get("board_class") != "i2c_pwm_only":
        raise SystemExit(f"{board_id} is {board.get('board_class')!r}, not an Arduino Mega (i2c_pwm_only) board")
    return board


def find_port(serial_id: str) -> str:
    """Port of the Mega whose USB serial is ``serial_id``; with none set, the only Mega plugged in."""
    megas = [p for p in list_ports.comports() if (p.vid, p.pid) == (MEGA_VID, MEGA_PID)]
    if serial_id:
        for p in megas:
            if p.serial_number == serial_id:
                return p.device
        raise SystemExit(
            f"no Arduino Mega with USB serial {serial_id} plugged in "
            f"(found: {', '.join(f'{p.device}={p.serial_number}' for p in megas) or 'none'})"
        )
    if len(megas) != 1:
        raise SystemExit(
            "serial_id is empty and "
            + (f"{len(megas)} Megas are plugged in: " + ", ".join(f"{p.device}={p.serial_number}" for p in megas)
               if megas else "no Mega is plugged in")
            + ". Set the board's serial_id, or pass --port."
        )
    log.warning(f"serial_id is empty: using the only Mega, {megas[0].device}. "
                f"Set serial_id: {megas[0].serial_number} in the YAML to pin this board.")
    return megas[0].device


def run(cmd: list[str], cwd: Path | None = None) -> None:
    log.info("$ " + " ".join(cmd))
    if subprocess.run(cmd, cwd=cwd, check=False).returncode != 0:
        raise SystemExit(f"failed: {cmd[0]}")


def main() -> int:
    enable_ansi()
    parser = argparse.ArgumentParser(description="Build and flash one Arduino Mega board")
    parser.add_argument("board", help="board id in the hardware YAML, e.g. mega_arms")
    parser.add_argument("--robot", default=os.environ.get("LUCY_ROBOT_PACKAGE", "inmoov_i2_urdf"),
                        help="robot package under src/ (default: $LUCY_ROBOT_PACKAGE or inmoov_i2_urdf)")
    parser.add_argument("--port", help="serial port to flash, instead of matching serial_id")
    parser.add_argument("--build-only", action="store_true", help="build without flashing")
    args = parser.parse_args()

    board = load_board(args.robot, args.board)
    for tool in ("avr-gcc", "avrdude"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} not found: install it on the host (e.g. dnf/apt install avr-gcc avrdude)")

    # Resolve the port first: a missing board should not wait for a build.
    port = None if args.build_only else args.port or find_port(str(board.get("serial_id") or "").strip())

    # The crate's rust-toolchain.toml and .cargo/config.toml resolve from cwd, not --manifest-path.
    configure_cargo_homes(require_pixi_env())
    run(["cargo", "build", "--release", "--features", str(board["compile_definition"])], cwd=MEGA_CRATE)
    if port is None:
        return 0

    # Same programmer settings ravedude uses for mega2560 (stk500v2 bootloader at 115200).
    run(["avrdude", "-p", "atmega2560", "-c", "wiring", "-P", port, "-b", "115200", "-D",
         "-U", f"flash:w:{MEGA_ELF}:e"])
    log.info(f"Flashed {args.board} on {port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
