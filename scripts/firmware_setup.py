#!/usr/bin/env python3
"""
Cross-platform firmware toolchain setup script.
Automatically installs rustup if missing, then sets up embedded toolchain.
"""
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# Allow `python scripts/firmware_setup.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_log import enable_ansi
from firmware_log import err
from firmware_log import info
from firmware_log import ok
from firmware_log import step
from firmware_log import warn


def is_windows():
    return platform.system() == "Windows"


def install_rustup_windows():
    """Download and run rustup-init.exe for Windows"""
    info("Downloading rustup-init.exe...")
    url = "https://win.rustup.rs/x86_64"
    rustup_init = Path.home() / "rustup-init.exe"

    try:
        urllib.request.urlretrieve(url, rustup_init)
        ok("Downloaded rustup-init.exe")

        info("Running rustup installer (this may take a few minutes)...")
        # Run with default profile (minimal), no PATH modification (we handle that)
        subprocess.run(
            [str(rustup_init), "-y", "--default-toolchain", "stable", "--profile", "minimal"],
            check=True,
            capture_output=True,
            text=True,
        )
        ok("rustup installed successfully")

        # Add to PATH for this session
        cargo_bin = Path.home() / ".cargo" / "bin"
        os.environ["PATH"] = f"{cargo_bin};{os.environ['PATH']}"

    except Exception as e:
        err(f"Failed to install rustup: {e}")
        info("Please install manually from https://rustup.rs")
        sys.exit(1)
    finally:
        if rustup_init.exists():
            rustup_init.unlink()


def install_rustup_unix():
    """Download and run rustup.sh for Unix (macOS/Linux)"""
    info("Downloading rustup installer...")
    url = "https://sh.rustup.rs"

    try:
        info("Running rustup installer (this may take a few minutes)...")
        # Pipe sh.rustup.rs directly to sh
        result = subprocess.run(
            ["curl", "--proto", "=https", "--tlsv1.2", "-sSf", url],
            capture_output=True,
            text=True,
            check=True,
        )

        # Run the script with -y for non-interactive
        subprocess.run(
            ["sh", "-s", "--", "-y", "--default-toolchain", "stable", "--profile", "minimal"],
            input=result.stdout,
            text=True,
            check=True,
        )
        ok("rustup installed successfully")

        # Add to PATH for this session
        cargo_bin = Path.home() / ".cargo" / "bin"
        os.environ["PATH"] = f"{cargo_bin}:{os.environ['PATH']}"

    except Exception as e:
        err(f"Failed to install rustup: {e}")
        info("Please install manually from https://rustup.rs")
        sys.exit(1)


def main():
    enable_ansi()
    info("=" * 60)
    info("Lucy Firmware Toolchain Setup")
    info("=" * 60)

    # Step 1: Check for rustup, install if missing
    step(1, 5, "Checking for rustup...")
    if not shutil.which("rustup"):
        warn("rustup not found - installing automatically...")
        if is_windows():
            install_rustup_windows()
        else:
            install_rustup_unix()

        # Verify installation
        if not shutil.which("rustup"):
            err("rustup installation failed")
            info("Please install manually from https://rustup.rs")
            sys.exit(1)
    else:
        ok("rustup already installed")
        # Show version
        result = subprocess.run(["rustup", "--version"], capture_output=True, text=True)
        info(f"  {result.stdout.strip()}")

    # Step 2: Install ARM Cortex-M0+ target for RP2040
    step(2, 5, "Installing thumbv6m-none-eabi target...")
    try:
        subprocess.run(
            ["rustup", "target", "add", "thumbv6m-none-eabi"],
            check=True,
            capture_output=True,
            text=True,
        )
        ok("ARM Cortex-M0+ target installed")
    except subprocess.CalledProcessError as e:
        err(f"Failed to install target: {e.stderr}")
        sys.exit(1)

    # Step 3: Install elf2uf2-rs for UF2 conversion
    step(3, 5, "Installing elf2uf2-rs...")
    try:
        # Check if already installed
        result = subprocess.run(
            ["cargo", "install", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        if "elf2uf2-rs" in result.stdout:
            ok("elf2uf2-rs already installed")
        else:
            info("  Installing elf2uf2-rs (this may take a few minutes)...")
            subprocess.run(
                ["cargo", "install", "elf2uf2-rs"],
                check=True,
            )
            ok("elf2uf2-rs installed")
    except subprocess.CalledProcessError as e:
        err(f"Failed to install elf2uf2-rs: {e}")
        sys.exit(1)

    # Step 4: Symlink/copy to Pixi environment
    step(4, 5, "Linking tools to Pixi environment...")
    try:
        conda_prefix = Path(os.environ.get("CONDA_PREFIX", ""))
        if not conda_prefix.exists():
            warn("CONDA_PREFIX not set - tools will only be in ~/.cargo/bin")
        else:
            cargo_bin = Path.home() / ".cargo" / "bin"
            if is_windows():
                # Windows: copy to Scripts directory
                pixi_bin = conda_prefix / "Scripts"
                pixi_bin.mkdir(exist_ok=True)
                src = cargo_bin / "elf2uf2-rs.exe"
                dst = pixi_bin / "elf2uf2-rs.exe"
                if src.exists():
                    shutil.copy(src, dst)
                    ok(f"Copied elf2uf2-rs.exe to {pixi_bin}")
            else:
                # Unix: symlink to bin directory
                pixi_bin = conda_prefix / "bin"
                pixi_bin.mkdir(exist_ok=True)
                src = cargo_bin / "elf2uf2-rs"
                dst = pixi_bin / "elf2uf2-rs"
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    dst.symlink_to(src)
                    ok(f"Symlinked elf2uf2-rs to {pixi_bin}")
    except Exception as e:
        warn(f"Could not link to Pixi environment: {e}")
        info("  Tools will still work from ~/.cargo/bin")

    # Step 5: Verify installation
    step(5, 5, "Verifying installation...")
    checks = [
        ("rustc", ["rustc", "--version"]),
        ("cargo", ["cargo", "--version"]),
        ("elf2uf2-rs", ["elf2uf2-rs", "--version"]),
    ]

    all_ok = True
    for name, cmd in checks:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = result.stdout.strip().split("\n")[0]
            ok(f"{name}: {version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            err(f"{name}: NOT FOUND")
            all_ok = False

    info("\n" + "=" * 60)
    if all_ok:
        ok("Firmware toolchain setup complete!")
        info("\nNext steps:")
        info("  - Build firmware: pixi run firmware-build")
        info("  - Flash boards:   pixi run firmware-flash")
    else:
        err("Setup incomplete - please fix errors above")
        sys.exit(1)
    info("=" * 60)


if __name__ == "__main__":
    main()
