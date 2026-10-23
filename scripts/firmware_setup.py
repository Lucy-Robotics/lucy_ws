#!/usr/bin/env python3
"""
Cross-platform firmware toolchain setup for Lucy.

Designed to be zero-touch under Pixi:

    pixi run firmware-setup

Installs rustup + thumbv6m-none-eabi + elf2uf2-rs into the **active Pixi env**
(``$CONDA_PREFIX/cargo`` + ``$CONDA_PREFIX/rustup``). No sudo for the toolchain.
``. "$HOME/.cargo/env"`` is not required. elf2uf2 is built without serial.

On Linux, also installs USB-serial udev rules (Pico + Feetech) when sudo is
available, and applies a temporary chmod on already-plugged matching TTYs so
host firmwares can open the port without dialout. Skip with
``LUCY_SKIP_USB_ACCESS=1``. Host binaries: ``pixi run firmware-build-linux``.

Do not run the whole script as root; sudo is only used for udev/chmod.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

from firmware_cargo_env import configure_cargo_homes
from firmware_cargo_env import is_windows
from firmware_cargo_env import require_pixi_env
from firmware_log import enable_ansi
from firmware_log import get_logger

log = get_logger()


def refuse_if_root() -> None:
    if is_windows():
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        log.error("Do not run firmware-setup as root / with sudo.")
        log.info("   Re-run as your user:  pixi run firmware-setup")
        sys.exit(1)


def rustup_init_url() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        # Always use the official rustup-init.exe bootstrapper.
        return "https://win.rustup.rs/x86_64"

    if system == "Darwin":
        triple = "aarch64-apple-darwin" if machine in ("arm64", "aarch64") else "x86_64-apple-darwin"
    elif system == "Linux":
        if machine in ("aarch64", "arm64"):
            triple = "aarch64-unknown-linux-gnu"
        elif machine in ("x86_64", "amd64"):
            triple = "x86_64-unknown-linux-gnu"
        else:
            raise RuntimeError(f"unsupported Linux arch for rustup-init: {machine}")
    else:
        raise RuntimeError(f"unsupported OS for rustup-init: {system}")

    return f"https://static.rust-lang.org/rustup/dist/{triple}/rustup-init"


def download(url: str, dest: Path) -> None:
    log.info(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "lucy-firmware-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def install_rustup(cargo_bin: Path) -> None:
    """Install rustup into CARGO_HOME / RUSTUP_HOME (already set)."""
    if shutil.which("rustup"):
        log.ok("rustup already installed (Pixi env)")
        result = subprocess.run(["rustup", "--version"], capture_output=True, text=True)
        log.info(f"   {result.stdout.strip()}")
        return

    log.warning("rustup not found in Pixi env - installing automatically...")
    url = rustup_init_url()
    if is_windows():
        init_path = Path.home() / "lucy-rustup-init.exe"
    else:
        init_path = Path(os.environ["CARGO_HOME"]) / "rustup-init"

    try:
        download(url, init_path)
        if not is_windows():
            init_path.chmod(init_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        log.info("Running rustup installer (this may take a few minutes)...")
        subprocess.run(
            [
                str(init_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
                "--no-modify-path",
            ],
            check=True,
        )
        log.ok("rustup installed into Pixi env")
    except Exception as e:
        log.error(f"Failed to install rustup: {e}")
        log.info("   Check network access to static.rust-lang.org")
        sys.exit(1)
    finally:
        if init_path.exists():
            init_path.unlink()

    if not (cargo_bin / ("rustup.exe" if is_windows() else "rustup")).exists():
        log.error("rustup binary missing after install")
        sys.exit(1)


def install_elf2uf2() -> None:
    """ELF→UF2 only — skip default serial feature (needs libudev on Linux)."""
    result = subprocess.run(
        ["cargo", "install", "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    if "elf2uf2-rs" in result.stdout:
        log.ok("elf2uf2-rs already installed")
        return

    log.info("   Installing elf2uf2-rs --no-default-features ...")
    subprocess.run(
        ["cargo", "install", "elf2uf2-rs", "--no-default-features"],
        check=True,
    )
    log.ok("elf2uf2-rs installed")


def load_usb_module():
    """firmware_usb_access, or None: a USB failure must not fail toolchain setup."""
    try:
        import importlib.util

        usb_path = Path(__file__).resolve().parent / "firmware_usb_access.py"
        spec = importlib.util.spec_from_file_location("firmware_usb_access", usb_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {usb_path}")
        usb_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(usb_mod)
        # Ask for sudo now rather than minutes later at the USB step.
        usb_mod.prime_sudo()
        return usb_mod
    except Exception as exc:  # pragma: no cover - never fail toolchain setup on USB ACL
        log.warning(f"USB access step failed (toolchain still OK): {exc}")
        return None


def main() -> None:
    enable_ansi()
    log.info("=" * 60)
    log.info("Lucy Firmware Toolchain Setup")
    log.info("=" * 60)

    refuse_if_root()
    usb_mod = load_usb_module()
    conda_prefix = require_pixi_env()
    cargo_bin = configure_cargo_homes(conda_prefix)
    log.info(f"Pixi env: {conda_prefix}")
    log.info(f"CARGO_HOME={os.environ['CARGO_HOME']}")
    log.info(f"RUSTUP_HOME={os.environ['RUSTUP_HOME']}")

    log.step(1, 4, "Checking for rustup...")
    install_rustup(cargo_bin)

    subprocess.run(["rustup", "default", "stable"], check=False, capture_output=True)

    log.step(2, 4, "Installing thumbv6m-none-eabi target...")
    try:
        subprocess.run(
            ["rustup", "target", "add", "thumbv6m-none-eabi"],
            check=True,
            capture_output=True,
            text=True,
        )
        log.ok("ARM Cortex-M0+ target installed")
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to install target: {e.stderr}")
        sys.exit(1)

    log.step(3, 4, "Installing elf2uf2-rs...")
    try:
        install_elf2uf2()
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to install elf2uf2-rs: {e}")
        sys.exit(1)

    log.step(4, 4, "Verifying installation...")
    checks: list[tuple[str, list[str] | None]] = [
        ("rustc", ["rustc", "--version"]),
        ("cargo", ["cargo", "--version"]),
        # elf2uf2-rs 2.x has no --version flag; presence + --help is enough.
        ("elf2uf2-rs", None),
    ]
    all_ok = True
    for name, cmd in checks:
        binary = cargo_bin / (f"{name}.exe" if is_windows() else name)
        if cmd is None:
            if binary.is_file() and os.access(binary, os.X_OK):
                log.ok(f"{name}: {binary}")
            else:
                log.error(f"{name}: NOT FOUND under {cargo_bin}")
                all_ok = False
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = result.stdout.strip().split("\n")[0]
            log.ok(f"{name}: {version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            log.error(f"{name}: NOT FOUND under {cargo_bin}")
            all_ok = False

    # Permanent udev when sudo works; temporary chmod for already-plugged boards.
    # Skip with LUCY_SKIP_USB_ACCESS=1. A USB failure must not fail toolchain setup.
    if usb_mod is not None:
        try:
            usb_mod.ensure_usb_access()
        except Exception as exc:  # pragma: no cover - never fail toolchain setup on USB ACL
            log.warning(f"USB access step failed (toolchain still OK): {exc}")

    log.info("\n" + "=" * 60)
    if all_ok:
        log.ok("Firmware toolchain setup complete!")
        log.info("   Tools live inside the Pixi env. No shell config needed.")
        log.info("\nNext:")
        log.info("  pixi run firmware-build         # RP2040 UF2")
        log.info("  pixi run firmware-build-linux   # host linux + mcu_bridge")
        log.info("  pixi run firmware-flash")
    else:
        log.error("Setup incomplete")
        sys.exit(1)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
