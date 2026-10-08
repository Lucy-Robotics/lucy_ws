#!/usr/bin/env python3
"""
Install USB access for Raspberry Pi Pico so ``picotool`` / CDC work without
interactive sudo during pipeline flash.

Linux (mutable /etc): udev under ``/etc/udev/rules.d`` + dialout + optional sudoers.
Linux (NixOS / read-only /etc): udev under ``/run/udev/rules.d`` (until reboot) —
no ``configuration.nix`` required. Re-run after reboot or use a login hook.
macOS / Windows: guidance only; exit 0.

Used by ``pixi run firmware-setup`` and can be run directly:

    python scripts/install_pico_usb_access.py
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RULES_NAME = "99-lucy-pico.rules"
SUDOERS_NAME = "99-lucy-picotool"
ETC_UDEV_DEST = Path("/etc/udev/rules.d") / RULES_NAME
RUN_UDEV_DEST = Path("/run/udev/rules.d") / RULES_NAME
SUDOERS_DEST = Path("/etc/sudoers.d") / SUDOERS_NAME

RULES_BODY = """\
# Lucy / Raspberry Pi Pico USB access (BOOTSEL + application CDC).
# Allows picotool + ttyACM without root.

# Raspberry Pi Pico native (VID 2e8a)
SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", ENV{ID_MM_DEVICE_IGNORE}="1"
KERNEL=="ttyACM*", ATTRS{idVendor}=="2e8a", MODE="0666", TAG+="uaccess"
KERNEL=="ttyUSB*", ATTRS{idVendor}=="2e8a", MODE="0666", TAG+="uaccess"

# Lucy Custom Servo2040 legacy (VID 16c0 / PID 27dd) — until boards upgrade to 2e8a
SUBSYSTEM=="usb", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="27dd", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="16c0", ATTRS{idProduct}=="27dd", ENV{ID_MM_DEVICE_IGNORE}="1"
KERNEL=="ttyACM*", ATTRS{idVendor}=="16c0", MODE="0666", TAG+="uaccess"
KERNEL=="ttyUSB*", ATTRS{idVendor}=="16c0", MODE="0666", TAG+="uaccess"
"""

def is_windows() -> bool:
    return platform.system() == "Windows"


def is_darwin() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def is_nixos() -> bool:
    return Path("/etc/NIXOS").is_file() or Path("/run/current-system").exists()


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    return sys.stdout.isatty()


def _paint(text: str, code: str) -> str:
    if not _color_enabled():
        return text
    return f"\033[{code}m{text}\033[0m"


def _tag_ok() -> str:
    return _paint("OK", "32;1")


def _tag_need() -> str:
    return _paint("NEED", "33;1")


def _tag_ko() -> str:
    return _paint("KO", "31;1")


def refuse_if_root() -> None:
    if is_windows():
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("❌ Do not run as root; re-run as your user (script uses sudo).")
        sys.exit(1)


def repo_rules_path() -> Path:
    return Path(__file__).resolve().parent / "udev" / RULES_NAME


def load_rules_text() -> str:
    path = repo_rules_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return RULES_BODY


def path_is_practically_writable(directory: Path) -> bool:
    """True if we can create a file there as root via a dry probe is hard;
    check mount options / known NixOS layout instead."""
    if not directory.exists():
        # /run/udev/rules.d may need to be created by root.
        return directory == Path("/run/udev/rules.d") or str(directory).startswith("/run/")
    try:
        # Non-root probe: if the mount is ro, open for write fails even for listing.
        st = os.statvfs(directory)
        if st.f_flag & getattr(os, "ST_RDONLY", 1):
            return False
    except OSError:
        pass
    # NixOS: /etc is often a bind of a read-only generation.
    if is_nixos() and str(directory).startswith("/etc"):
        return False
    return True


def run_sudo(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sudo", *argv], check=check, text=True, capture_output=False)


def install_udev_rules(rules_text: str, dest: Path) -> None:
    print(f"→ Installing {dest} (sudo)...")
    text = rules_text if rules_text.endswith("\n") else rules_text + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".rules") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    try:
        run_sudo(["mkdir", "-p", str(dest.parent)])
        run_sudo(["install", "-m", "0644", str(tmp_path), str(dest)])
    finally:
        tmp_path.unlink(missing_ok=True)
    run_sudo(["udevadm", "control", "--reload-rules"], check=False)
    run_sudo(["udevadm", "trigger"], check=False)


def ensure_dialout_linux() -> None:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not user:
        print("⚠️  Could not determine USER — skip dialout")
        return
    try:
        subprocess.run(
            ["getent", "group", "dialout"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ℹ️  No dialout group — udev TAG+=uaccess should grant seat access.")
        return

    try:
        groups_out = subprocess.run(
            ["id", "-nG", user],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        groups_out = []

    if "dialout" in groups_out:
        print("✅ already in dialout")
        return

    if is_nixos():
        print(
            "ℹ️  NixOS: dialout via usermod is ephemeral / may conflict with declarative users."
        )
        print("   Prefer users.users.<name>.extraGroups = [ \"dialout\" ]; if you manage users in Nix.")
        print("   With TAG+=uaccess, a local seat session often needs no dialout.")
        return

    print(f"→ Adding {user} to dialout (re-login required)...")
    run_sudo(["usermod", "-aG", "dialout", user])
    print("⚠️  Log out and back in (or reboot) so dialout membership applies.")


def install_sudoers_picotool_linux() -> bool:
    """Return True if sudoers was installed. Skip on NixOS / RO /etc."""
    if is_nixos() or not path_is_practically_writable(Path("/etc/sudoers.d")):
        print("ℹ️  Skipping sudoers drop-in (NixOS or read-only /etc).")
        print("   Prefer udev uaccess so the pipeline never needs sudo.")
        return False

    picotool = shutil.which("picotool")
    if not picotool:
        print("⚠️  picotool not on PATH — skip sudoers. Install picotool then re-run.")
        return False

    print(f"→ Installing optional passwordless sudo for picotool → {picotool}")
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    line = f"{user} ALL=(ALL) NOPASSWD: {picotool}\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".sudoers") as tmp:
        tmp.write(line)
        tmp_path = Path(tmp.name)
    try:
        run_sudo(["install", "-m", "0440", str(tmp_path), str(SUDOERS_DEST)])
    finally:
        tmp_path.unlink(missing_ok=True)

    check = subprocess.run(
        ["sudo", "visudo", "-cf", str(SUDOERS_DEST)],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(f"❌ sudoers validation failed — removing {SUDOERS_DEST}")
        print(check.stderr or check.stdout)
        run_sudo(["rm", "-f", str(SUDOERS_DEST)], check=False)
        return False
    print(f"✅ sudoers OK ({SUDOERS_DEST})")
    return True


def print_non_linux_guidance(*, quiet: bool = False) -> None:
    system = platform.system()
    if quiet:
        print(f"  {_tag_ok()}    Pico USB: no udev on {system}")
        return
    print(f"⏭️  Pico USB system install is Linux-only (this host: {system}).")
    if is_windows():
        print("   Windows: install picotool via your package manager / scoop / cargo,")
        print("   and use Zadig WinUSB for the Pico in BOOTSEL if picotool cannot open it.")
        print("   Pipeline flash uses picotool without sudo on Windows.")
    elif is_darwin():
        print("   macOS: brew install picotool; USB access normally needs no udev.")
        print("   Pipeline flash uses picotool without sudo.")
    print("   See lucy_config_pipeline/README.md — Pico USB access.")


def print_nixos_optional_declarative(rules_text: str) -> None:
    print()
    print("Optional (persistent across reboot, only if you want it in Nix):")
    print("  services.udev.extraRules = ''")
    for line in rules_text.strip().splitlines():
        print(f"    {line}")
    print("  '';")
    print("  # then: sudo nixos-rebuild switch")
    print("Not required if you re-run this script after each reboot.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lucy Pico USB access (udev / dialout)")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output for embedding under firmware-setup",
    )
    args = parser.parse_args(argv)
    quiet = args.quiet

    if not quiet:
        print("=" * 60)
        print("Lucy Pico USB access setup")
        print("=" * 60)

    refuse_if_root()

    if not is_linux():
        print_non_linux_guidance(quiet=quiet)
        return 0

    rules_text = load_rules_text()
    force = os.environ.get("LUCY_PICO_USB_FORCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    use_run = is_nixos() or not path_is_practically_writable(Path("/etc/udev/rules.d"))
    dest = RUN_UDEV_DEST if use_run else ETC_UDEV_DEST

    if use_run and not quiet:
        print("ℹ️  NixOS / read-only /etc detected — installing udev rules to /run")
        print("   (survives until reboot; no configuration.nix required).")

    if dest.is_file() and not force:
        existing = dest.read_text(encoding="utf-8")
        if existing.rstrip("\n") + "\n" == (rules_text.rstrip("\n") + "\n"):
            if quiet:
                print(f"  {_tag_ok()}    Pico USB udev ({dest})")
                return 0
            print(f"✅ udev rules already present: {dest}")
            if use_run:
                print("   Note: /run rules last until reboot; re-run this script after reboot if needed.")
            ensure_dialout_linux()
            install_sudoers_picotool_linux()
            print("\n✅ Pico USB access check complete.")
            print("   Test: picotool info -a")
            return 0
        if not quiet:
            print(f"→ Updating outdated udev rules at {dest}")

    if not quiet:
        print("   Pipeline flash uses `picotool` without sudo when USB udev rules are installed.")
    try:
        if quiet:
            print(f"        installing udev → {dest} (may prompt for sudo)…")
        install_udev_rules(rules_text, dest)
    except subprocess.CalledProcessError as e:
        print(f"  {_tag_ko()}    Could not install udev rules to {dest}: {e}")
        if use_run:
            print("        Need one successful sudo this boot.")
        else:
            print("        Flash fallback: LUCY_PIPELINE_FLASH_USE_SUDO=1")
        return 1

    if quiet:
        print(f"  {_tag_ok()}    Pico USB udev ({dest})")
        return 0

    ensure_dialout_linux()
    install_sudoers_picotool_linux()

    print()
    print(f"✅ Pico USB access installed → {dest}")
    if use_run:
        print("   Replug the Pico. Rules last until reboot; then re-run this script.")
        print_nixos_optional_declarative(rules_text)
    else:
        print("   Replug the Pico (or reboot) after first install.")
    print("   Test: picotool info -a   # should work without sudo in BOOTSEL")
    print("   Test: ls /dev/serial/by-id/")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"❌ Pico USB access install failed: {e}")
        print("   Flash may still work with: LUCY_PIPELINE_FLASH_USE_SUDO=1")
        raise SystemExit(1) from e
