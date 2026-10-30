#!/usr/bin/env python3
"""Grant local access to Lucy USB devices (Pico CDC/BOOTSEL + Feetech dongle).

Used by ``firmware_setup`` / ``pixi run setup-udev``:

1. Prefer permanent: install ``config/udev/*.rules`` under ``/etc/udev/rules.d``
   (sudo once) and reload udev — tty CDC, raw USB (picotool), and RPI-RP2 block
   device so the flash pipeline never needs sudo at runtime.
2. On NixOS (immutable ``/etc/udev``): print a host-specific ``configuration.nix``
   snippet (absolute rules path + current user) to copy/paste, then
   ``sudo nixos-rebuild switch``.
3. Always attempt temporary: ``chmod 0666`` on currently plugged matching TTYs
   so the current session works without replug / dialout.

Skip with ``LUCY_SKIP_USB_ACCESS=1``. Non-Linux hosts are a no-op.
"""
from __future__ import annotations

import getpass
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

# Must match firmwares/linux board.rs and firmwares/mcu_bridge / rp2040 USB IDs.
LUCY_USB_IDS: tuple[tuple[str, str, str], ...] = (
    ("2e8a", "0003", "Raspberry Pi Pico CDC"),
    ("1a86", "55d3", "Feetech USB Single Serial"),
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
UDEV_SOURCE_DIR = WORKSPACE_ROOT / "config" / "udev"
UDEV_TARGET_DIR = Path("/etc/udev/rules.d")
OBSOLETE_RULE = UDEV_TARGET_DIR / "99-lucy-rp2040.rules"
# Unique line from config/udev/99-lucy-usb-serial.rules (present after NixOS rebuild).
LUCY_UDEV_MARKER = "Lucy USB access without dialout"


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


def matching_usb_nodes() -> list[tuple[Path, str, str, str]]:
    """List (/dev/bus/usb/BBB/DDD, vid, pid, label) for picotool force-reset."""
    wanted = {(v, p): label for v, p, label in LUCY_USB_IDS}
    found: list[tuple[Path, str, str, str]] = []
    root = Path("/sys/bus/usb/devices")
    if not root.is_dir():
        return found
    for entry in root.iterdir():
        vid_path = entry / "idVendor"
        pid_path = entry / "idProduct"
        if not vid_path.is_file() or not pid_path.is_file():
            continue
        try:
            vid = vid_path.read_text(encoding="utf-8").strip().lower().zfill(4)[-4:]
            pid = pid_path.read_text(encoding="utf-8").strip().lower().zfill(4)[-4:]
            bus = int((entry / "busnum").read_text(encoding="utf-8").strip())
            addr = int((entry / "devnum").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        label = wanted.get((vid, pid))
        if not label:
            continue
        node = Path(f"/dev/bus/usb/{bus:03d}/{addr:03d}")
        if node.exists():
            found.append((node, vid, pid, label))
    return found


def is_nixos() -> bool:
    """True when ``/etc/udev/rules.d`` is the NixOS store symlink (or ``/etc/NIXOS``)."""
    if Path("/etc/NIXOS").exists():
        return True
    try:
        return Path("/etc/udev/rules.d").resolve().as_posix().startswith("/nix/store/")
    except OSError:
        return False


def current_username() -> str:
    for key in ("USER", "LOGNAME", "USERNAME"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    try:
        return getpass.getuser()
    except Exception:
        return "<you>"


def nixos_configuration_snippet() -> str:
    """Host-specific NixOS fragment ready to paste into configuration.nix / a flake."""
    rules = (UDEV_SOURCE_DIR / "99-lucy-usb-serial.rules").resolve()
    user = current_username()
    return (
        "programs.nix-ld.enable = true;\n"
        f'services.udev.extraRules = builtins.readFile "{rules}";\n'
        f'users.users.{user}.extraGroups = [ "dialout" ];\n'
    )


def lucy_udev_rules_active() -> bool:
    """True when Lucy USB udev rules are already loaded into the running system."""
    roots = (
        Path("/etc/udev/rules.d"),
        Path("/run/current-system/etc/udev/rules.d"),
    )
    for root in roots:
        if not root.is_dir():
            continue
        try:
            paths = list(root.glob("*.rules"))
        except OSError:
            continue
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if LUCY_UDEV_MARKER in text:
                return True
    return False


def user_in_dialout() -> bool:
    """True when the current user is in the dialout group (effective or configured)."""
    try:
        import grp
    except ImportError:
        return False
    try:
        dialout = grp.getgrnam("dialout")
    except KeyError:
        return True  # no dialout group on this system
    user = current_username()
    if user in dialout.gr_mem:
        return True
    try:
        return dialout.gr_gid in os.getgroups()
    except OSError:
        return False


def nixos_usb_already_configured() -> bool:
    """Skip the MANUAL SETUP prompt when Lucy USB udev rules are already active.

    Dialout is checked only for a soft hint: group membership needs a re-login
    after rebuild, so it must not re-trigger the banner.
    """
    return lucy_udev_rules_active()


def prompt_nixos_udev_config(*, allow_prompt: bool) -> None:
    """Print a copy/paste NixOS config block with absolute paths for this machine."""
    # Plain stdout: eye-catching banner + clean copy/paste (no log prefixes).
    sys.stdout.write(
        "\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        "!!!                                                      !!!\n"
        "!!!            MANUAL SETUP REQUIRED                     !!!\n"
        "!!!                                                      !!!\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        "\n"
        "NixOS: paste into configuration.nix (or a flake module):\n"
        "\n"
    )
    sys.stdout.write(nixos_configuration_snippet())
    sys.stdout.write(
        "\n"
        "Then:  sudo nixos-rebuild switch   (re-login + replug USB)\n"
        "\n"
    )
    sys.stdout.flush()
    if allow_prompt and sys.stdin.isatty():
        try:
            input("Press Enter to continue… ")
        except EOFError:
            pass


def install_udev_rules(*, allow_prompt: bool) -> bool:
    """Install config/udev/*.rules permanently. Returns True on success."""
    rules = sorted(UDEV_SOURCE_DIR.glob("*.rules"))
    if not rules:
        log.error(f"no udev rules under {UDEV_SOURCE_DIR}")
        return False

    if is_nixos():
        if nixos_usb_already_configured():
            return True
        prompt_nixos_udev_config(allow_prompt=allow_prompt)
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
        _sudo(["udevadm", "trigger", "--subsystem-match=usb"], allow_prompt=allow_prompt)
        _sudo(["udevadm", "trigger", "--subsystem-match=block"], allow_prompt=allow_prompt)
    return True


def _chmod_node(node: Path, label: str, *, allow_prompt: bool, fixed: list[Path]) -> None:
    try:
        if os.access(node, os.R_OK | os.W_OK):
            log.ok(f"already accessible: {node} ({label})")
            fixed.append(node)
            return
    except OSError:
        pass

    try:
        os.chmod(node, 0o666)
        log.ok(f"temporary access (chmod): {node} ({label})")
        fixed.append(node)
        return
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


def apply_temporary_access(*, allow_prompt: bool) -> list[Path]:
    """chmod 0666 matching TTYs + raw USB nodes (picotool) for this session."""
    fixed: list[Path] = []
    for node, _vid, _pid, label in matching_tty_nodes():
        _chmod_node(node, label, allow_prompt=allow_prompt, fixed=fixed)
    for node, _vid, _pid, label in matching_usb_nodes():
        _chmod_node(node, f"{label} [usb]", allow_prompt=allow_prompt, fixed=fixed)
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
    if is_nixos():
        if nixos_usb_already_configured():
            log.ok("NixOS USB access already configured — skipping setup prompt")
            permanent = True
            if not user_in_dialout():
                log.info("dialout not active in this session yet — re-login if CDC is still locked")
        else:
            prompt_nixos_udev_config(allow_prompt=allow_prompt)
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
