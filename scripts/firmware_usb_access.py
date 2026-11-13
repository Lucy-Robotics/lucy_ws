#!/usr/bin/env python3
"""Grant local access to Lucy USB-serial devices (Pico CDC + Feetech host dongle).

Used by ``firmware_setup`` / ``pixi run setup-udev``:

1. Prefer permanent: install ``config/udev/*.rules`` under ``/etc/udev/rules.d``
   (sudo) and reload udev.
2. Always attempt temporary: ``chmod 0666`` on currently plugged matching TTYs
   so the current session works without replug / dialout.

Skip with ``LUCY_SKIP_USB_ACCESS=1``. Non-Linux hosts are a no-op.
"""
from __future__ import annotations

import filecmp
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from firmware_log import enable_ansi
from firmware_log import get_logger

log = get_logger()

# Must match firmwares/linux board.rs and firmwares/mcu_bridge / rp2040 / arduino_mega USB IDs.
LUCY_USB_IDS: tuple[tuple[str, str, str], ...] = (
    ("2e8a", "0003", "Raspberry Pi Pico CDC"),
    ("1a86", "55d3", "Feetech USB Single Serial"),
    ("2341", "0042", "Arduino Mega 2560"),
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
UDEV_SOURCE_DIR = WORKSPACE_ROOT / "config" / "udev"
UDEV_TARGET_DIR = Path("/etc/udev/rules.d")
OBSOLETE_RULE = UDEV_TARGET_DIR / "99-lucy-rp2040.rules"


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _sudo_available_noninteractive() -> bool:
    if shutil.which("sudo") is None:
        return False
    return _run(["sudo", "-n", "true"]).returncode == 0


def _sudo(cmd: list[str], *, allow_prompt: bool) -> subprocess.CompletedProcess[str]:
    if os.geteuid() == 0:  # type: ignore[attr-defined]
        return _run(cmd)
    if shutil.which("sudo") is None:
        return subprocess.CompletedProcess(cmd, 127, "", "sudo not found")
    prefix = ["sudo"] if allow_prompt else ["sudo", "-n"]
    return _run(prefix + cmd)


def tty_usb_ids(node: Path) -> tuple[str, str] | None:
    """Return (vid, pid) lowercase hex for a tty device, or None."""
    if shutil.which("udevadm") is None:
        return None
    result = _run(
        ["udevadm", "info", "-q", "property", "-n", str(node)],
    )
    if result.returncode != 0:
        return None
    props: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key.strip().lower()] = value.strip().lower()
    vid = props.get("id_vendor_id") or props.get("idvendor")
    pid = props.get("id_model_id") or props.get("idproduct")
    if not vid or not pid:
        return None
    return vid.zfill(4)[-4:], pid.zfill(4)[-4:]


def matching_tty_nodes() -> list[tuple[Path, str, str, str]]:
    """List (path, vid, pid, label) for plugged Lucy USB-serial devices."""
    wanted = {(v, p): label for v, p, label in LUCY_USB_IDS}
    found: list[tuple[Path, str, str, str]] = []
    for pattern in ("ttyACM*", "ttyUSB*"):
        for node in sorted(Path("/dev").glob(pattern)):
            ids = tty_usb_ids(node)
            if ids is None:
                continue
            label = wanted.get(ids)
            if label:
                found.append((node, ids[0], ids[1], label))
    return found


def udev_rules_installed() -> bool:
    """True when every config/udev rule is already in /etc/udev/rules.d, unchanged (no sudo needed to check)."""
    rules = sorted(UDEV_SOURCE_DIR.glob("*.rules"))
    try:
        return bool(rules) and not OBSOLETE_RULE.exists() and all(
            filecmp.cmp(src, UDEV_TARGET_DIR / src.name, shallow=False) for src in rules
        )
    except OSError:
        return False


def prime_sudo() -> None:
    """Ask for the sudo password once, up front, only if ensure_usb_access() will need it."""
    if (
        env_flag("LUCY_SKIP_USB_ACCESS")
        or platform.system() != "Linux"
        or os.geteuid() == 0  # type: ignore[attr-defined]
        or not sys.stdin.isatty()
        or shutil.which("sudo") is None
        or udev_rules_installed()
    ):
        return
    log.info("USB udev rules need installing: sudo will ask for your password once, now.")
    subprocess.run(["sudo", "-v"], check=False)


def install_udev_rules(*, allow_prompt: bool) -> bool:
    """Install config/udev/*.rules permanently. Returns True on success."""
    rules = sorted(UDEV_SOURCE_DIR.glob("*.rules"))
    if not rules:
        log.error(f"no udev rules under {UDEV_SOURCE_DIR}")
        return False

    for src in rules:
        dest = UDEV_TARGET_DIR / src.name
        result = _sudo(["install", "-m", "0644", str(src), str(dest)], allow_prompt=allow_prompt)
        if result.returncode != 0:
            log.warning(f"could not install {src.name}: {result.stderr.strip() or result.stdout.strip()}")
            return False
        log.ok(f"installed {dest}")

    if OBSOLETE_RULE.exists() or _sudo(["test", "-f", str(OBSOLETE_RULE)], allow_prompt=False).returncode == 0:
        _sudo(["rm", "-f", str(OBSOLETE_RULE)], allow_prompt=allow_prompt)

    if shutil.which("udevadm"):
        _sudo(["udevadm", "control", "--reload-rules"], allow_prompt=allow_prompt)
        _sudo(["udevadm", "trigger", "--subsystem-match=tty"], allow_prompt=allow_prompt)
    return True


def apply_temporary_access(*, allow_prompt: bool) -> list[Path]:
    """chmod 0666 matching TTYs so this session can open them without dialout."""
    fixed: list[Path] = []
    for node, _vid, _pid, label in matching_tty_nodes():
        try:
            if os.access(node, os.R_OK | os.W_OK):
                log.ok(f"already accessible: {node} ({label})")
                fixed.append(node)
                continue
        except OSError:
            pass

        try:
            os.chmod(node, 0o666)
            log.ok(f"temporary access (chmod): {node} ({label})")
            fixed.append(node)
            continue
        except PermissionError:
            pass

        result = _sudo(["chmod", "0666", str(node)], allow_prompt=allow_prompt)
        if result.returncode == 0:
            log.ok(f"temporary access (sudo chmod): {node} ({label})")
            fixed.append(node)
        else:
            log.error(
                f"cannot chmod {node} ({label}): "
                f"{result.stderr.strip() or 'permission denied'}"
            )
    return fixed


def ensure_usb_access(*, allow_prompt: bool | None = None) -> None:
    """Permanent udev install when possible, then temporary chmod for plugged devices."""
    if env_flag("LUCY_SKIP_USB_ACCESS"):
        log.info("USB access: LUCY_SKIP_USB_ACCESS set — skipping")
        return
    if platform.system() != "Linux":
        log.info("USB access: not Linux — skipping udev/chmod")
        return

    if allow_prompt is None:
        # Prompt only when a TTY is attached (interactive Lucy Install / shell).
        allow_prompt = sys.stdin.isatty()

    log.step(5, 5, "USB serial access (Pico CDC + Feetech)...")
    permanent = False
    if udev_rules_installed():
        log.ok("udev rules already installed")
    elif _sudo_available_noninteractive() or allow_prompt:
        permanent = install_udev_rules(allow_prompt=allow_prompt)
        if permanent:
            log.ok("permanent udev rules installed / reloaded")
        elif not allow_prompt:
            log.warning(
                "permanent udev install needs sudo. Re-run interactively:\n"
                "     pixi run setup-udev\n"
                "   or: pixi run firmware-setup"
            )
    else:
        log.warning(
            "sudo not available non-interactively; skipping permanent udev rules.\n"
            "   Run later: pixi run setup-udev"
        )

    plugged = matching_tty_nodes()
    if not plugged:
        log.info("no Lucy USB-serial devices plugged in right now")
        log.info("   After plugging Feetech (1a86:55d3) or Pico (2e8a:0003), re-run:")
        log.info("     pixi run firmware-setup")
        return

    fixed = apply_temporary_access(allow_prompt=allow_prompt)
    if fixed:
        log.ok(f"temporary access ready for {len(fixed)} device(s)")
    else:
        log.error("plugged Lucy USB device(s) found but not writable for this user")
        log.info("   Fix: pixi run setup-udev   (or add your user to the dialout group)")


def main() -> int:
    enable_ansi()
    ensure_usb_access()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
