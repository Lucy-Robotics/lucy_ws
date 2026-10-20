#!/usr/bin/env python3
"""
Point rustup/cargo at the active Pixi env, then exec a command.

Multi-platform replacement for former firmware_cargo_env.sh / .bat activation
hooks. Pixi firmware tasks invoke this so cargo/rustc/elf2uf2-rs resolve under
``$CONDA_PREFIX/{cargo,rustup}`` without platform-specific shell scripts.

Usage::

    python scripts/firmware_cargo_env.py cargo build --release ...
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return platform.system() == "Windows"


def require_pixi_env() -> Path:
    """Firmware tools live in the Pixi env; refuse bare python runs."""
    prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if not prefix:
        print("❌ CONDA_PREFIX is unset.")
        print("   Run via Pixi so the toolchain stays inside the workspace env:")
        print("     pixi run firmware-setup")
        sys.exit(1)
    return Path(prefix)


def configure_cargo_homes(conda_prefix: Path) -> Path:
    """Isolate rustup/cargo under the Pixi env and put bins on PATH."""
    cargo_home = conda_prefix / "cargo"
    rustup_home = conda_prefix / "rustup"
    cargo_home.mkdir(parents=True, exist_ok=True)
    rustup_home.mkdir(parents=True, exist_ok=True)

    os.environ["CARGO_HOME"] = str(cargo_home)
    os.environ["RUSTUP_HOME"] = str(rustup_home)

    cargo_bin = cargo_home / "bin"
    cargo_bin.mkdir(parents=True, exist_ok=True)
    sep = ";" if is_windows() else ":"
    path = os.environ.get("PATH", "")
    prefix = str(cargo_bin)
    if not path.startswith(prefix + sep) and path != prefix:
        os.environ["PATH"] = f"{prefix}{sep}{path}" if path else prefix
    return cargo_bin


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python scripts/firmware_cargo_env.py <command> [args...]",
            file=sys.stderr,
        )
        return 2

    configure_cargo_homes(require_pixi_env())
    try:
        completed = subprocess.run(args, check=False)
    except FileNotFoundError:
        print(f"❌ command not found: {args[0]}", file=sys.stderr)
        print("   Run: pixi run firmware-setup", file=sys.stderr)
        return 127
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
