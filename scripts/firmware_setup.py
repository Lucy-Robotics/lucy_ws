#!/usr/bin/env python3
"""
Cross-platform firmware toolchain setup for Lucy.

Designed to be zero-touch under Pixi:

    pixi run firmware-setup

Installs rustup + thumbv6m-none-eabi + elf2uf2-rs into the **active Pixi env**
(``$CONDA_PREFIX/cargo`` + ``$CONDA_PREFIX/rustup``). No sudo, no manual
``. "$HOME/.cargo/env"``, no system libudev (elf2uf2 built without serial).

Do not run with sudo.
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


def is_windows() -> bool:
    return platform.system() == "Windows"


def refuse_if_root() -> None:
    if is_windows():
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("❌ Do not run firmware-setup as root / with sudo.")
        print("   Re-run as your user:  pixi run firmware-setup")
        sys.exit(1)


def require_pixi_env() -> Path:
    """Firmware tools install into the Pixi env; refuse bare python runs."""
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
    print(f"📥 Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "lucy-firmware-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def install_rustup(cargo_bin: Path) -> None:
    """Install rustup into CARGO_HOME / RUSTUP_HOME (already set)."""
    if shutil.which("rustup"):
        print("✅ rustup already installed (Pixi env)")
        result = subprocess.run(["rustup", "--version"], capture_output=True, text=True)
        print(f"   {result.stdout.strip()}")
        return

    print("⚠️  rustup not found in Pixi env — installing automatically...")
    url = rustup_init_url()
    if is_windows():
        init_path = Path.home() / "lucy-rustup-init.exe"
    else:
        init_path = Path(os.environ["CARGO_HOME"]) / "rustup-init"

    try:
        download(url, init_path)
        if not is_windows():
            init_path.chmod(init_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        print("🔧 Running rustup installer (this may take a few minutes)...")
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
        print("✅ rustup installed into Pixi env")
    except Exception as e:
        print(f"❌ Failed to install rustup: {e}")
        print("   Check network access to static.rust-lang.org")
        sys.exit(1)
    finally:
        if init_path.exists():
            init_path.unlink()

    if not (cargo_bin / ("rustup.exe" if is_windows() else "rustup")).exists():
        print("❌ rustup binary missing after install")
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
        print("✅ elf2uf2-rs already installed")
        return

    print("   Installing elf2uf2-rs --no-default-features ...")
    subprocess.run(
        ["cargo", "install", "elf2uf2-rs", "--no-default-features"],
        check=True,
    )
    print("✅ elf2uf2-rs installed")


def main() -> None:
    print("=" * 60)
    print("Lucy Firmware Toolchain Setup")
    print("=" * 60)

    refuse_if_root()
    conda_prefix = require_pixi_env()
    cargo_bin = configure_cargo_homes(conda_prefix)
    print(f"📦 Pixi env: {conda_prefix}")
    print(f"📦 CARGO_HOME={os.environ['CARGO_HOME']}")
    print(f"📦 RUSTUP_HOME={os.environ['RUSTUP_HOME']}")

    print("\n1️⃣ Checking for rustup...")
    install_rustup(cargo_bin)

    subprocess.run(["rustup", "default", "stable"], check=False, capture_output=True)

    print("\n2️⃣ Installing thumbv6m-none-eabi target...")
    try:
        subprocess.run(
            ["rustup", "target", "add", "thumbv6m-none-eabi"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("✅ ARM Cortex-M0+ target installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install target: {e.stderr}")
        sys.exit(1)

    print("\n3️⃣ Installing elf2uf2-rs...")
    try:
        install_elf2uf2()
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install elf2uf2-rs: {e}")
        sys.exit(1)

    print("\n4️⃣ Verifying installation...")
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
                print(f"✅ {name}: {binary}")
            else:
                print(f"❌ {name}: NOT FOUND under {cargo_bin}")
                all_ok = False
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = result.stdout.strip().split("\n")[0]
            print(f"✅ {name}: {version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"❌ {name}: NOT FOUND under {cargo_bin}")
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("✅ Firmware toolchain setup complete!")
        print("   Tools live inside the Pixi env — no shell config needed.")
        print("\nNext:")
        print("  pixi run firmware-build")
        print("  pixi run firmware-flash")
    else:
        print("❌ Setup incomplete")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
