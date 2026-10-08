#!/usr/bin/env python3
"""
Cross-platform firmware toolchain setup for Lucy.

Designed to be zero-touch under Pixi:

    pixi run firmware-setup
    pixi run firmware-check

Installs rustup + thumbv6m-none-eabi + elf2uf2-rs into the **active Pixi env**
(``$CONDA_PREFIX/cargo`` + ``$CONDA_PREFIX/rustup``). No sudo, no manual
``. "$HOME/.cargo/env"``, no system libudev (elf2uf2 built without serial).

Do not run with sudo.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

THUMBV6_TARGET = "thumbv6m-none-eabi"

# Official Raspberry Pi prebuilt picotool (pico-sdk-tools releases).
PICOTOOL_VERSION = "2.3.1"
PICOTOOL_TOOLS_TAG = "v2.3.1-0"

SETUP_HINT = (
    "Fix:  pixi run firmware-setup\n"
    "  or:  python3 install.py"
)

# Pico USB rule locations (must match install_pico_usb_access.py).
_ETC_UDEV = Path("/etc/udev/rules.d/99-lucy-pico.rules")
_RUN_UDEV = Path("/run/udev/rules.d/99-lucy-pico.rules")


def is_windows() -> bool:
    return platform.system() == "Windows"


def refuse_if_root() -> None:
    if is_windows():
        return
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        _fail("Do not run firmware-setup as root / with sudo.")
        print("      Re-run as your user:  pixi run firmware-setup")
        sys.exit(1)


def require_pixi_env() -> Path:
    """Firmware tools install into the Pixi env; refuse bare python runs."""
    prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if not prefix:
        _fail("CONDA_PREFIX is unset.")
        print("      Run via Pixi:  pixi run firmware-setup")
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


def _exe(name: str) -> str:
    return f"{name}.exe" if is_windows() else name


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("LUCY_FIRMWARE_SETUP_COLOR", "").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return False
    return sys.stdout.isatty()


def _paint(text: str, code: str) -> str:
    if not _color_enabled():
        return text
    return f"\033[{code}m{text}\033[0m"


def _ok(msg: str) -> None:
    print(f"  {_paint('OK', '32;1')}    {msg}")


def _need(msg: str) -> None:
    print(f"  {_paint('NEED', '33;1')}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {_paint('KO', '31;1')}    {msg}")


def _result_ok(msg: str) -> None:
    print(f"Result: {_paint('OK', '32;1')} — {msg}")


def _result_ko(msg: str) -> None:
    print(f"Result: {_paint('KO', '31;1')} — {msg}")


def _run_quiet(cmd: list[str], *, what: str) -> None:
    """Run a command; capture output; only print it on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout or "").strip()
    _fail(f"{what} failed (exit {result.returncode})")
    if detail:
        for line in detail.splitlines()[-20:]:
            print(f"        {line}")
    raise SystemExit(1)


def check_firmware_toolchain() -> list[str]:
    """Return human-readable missing items; empty list means ready.

    Does not install anything. When ``CONDA_PREFIX`` is set, configures cargo
    homes on PATH so checks match a Pixi-activated shell.
    """
    errors: list[str] = []
    prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if not prefix:
        errors.append(
            "CONDA_PREFIX is unset (run via Pixi: pixi run firmware-check / firmware-setup)"
        )
        return errors

    cargo_bin = configure_cargo_homes(Path(prefix))

    for name in ("rustup", "rustc", "cargo"):
        if shutil.which(name) is None:
            errors.append(f"{name} not found under {cargo_bin}")

    if shutil.which("rustup") is not None:
        result = subprocess.run(
            ["rustup", "target", "list", "--installed"],
            capture_output=True,
            text=True,
            check=False,
        )
        installed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if result.returncode != 0 or THUMBV6_TARGET not in installed:
            errors.append(
                f"rustup target {THUMBV6_TARGET} not installed "
                f"(run: rustup target add {THUMBV6_TARGET})"
            )

    elf = cargo_bin / _exe("elf2uf2-rs")
    if not (elf.is_file() and os.access(elf, os.X_OK)):
        if shutil.which("elf2uf2-rs") is None:
            errors.append(f"elf2uf2-rs not found under {cargo_bin}")

    if shutil.which("picotool") is None:
        errors.append(
            "picotool not found on PATH "
            "(run: pixi run firmware-setup — installs Raspberry Pi picotool into the Pixi env)"
        )

    return errors


def print_check_result(errors: list[str]) -> int:
    """Print check outcome; return process exit code (0 = ready)."""
    if not errors:
        print(f"{_paint('OK', '32;1')}  Firmware toolchain ready")
        return 0
    print(f"{_paint('KO', '31;1')}  Firmware toolchain not ready:")
    for item in errors:
        print(f"      - {item}")
    print()
    print(SETUP_HINT)
    return 1


def rustup_init_url() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        # win.rustup.rs hosts both arches; prefer native on Windows ARM.
        if machine in ("aarch64", "arm64"):
            return "https://win.rustup.rs/aarch64"
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
    req = urllib.request.Request(url, headers={"User-Agent": "lucy-firmware-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def install_rustup(cargo_bin: Path) -> str:
    """Install rustup if needed. Returns status label for the checklist."""
    if shutil.which("rustup"):
        ver = subprocess.run(
            ["rustc", "--version"], capture_output=True, text=True, check=False
        )
        label = (ver.stdout or "").strip() or "present"
        return f"rustup ({label})"

    url = rustup_init_url()
    if is_windows():
        init_path = Path.home() / "lucy-rustup-init.exe"
    else:
        init_path = Path(os.environ["CARGO_HOME"]) / "rustup-init"

    try:
        print("        downloading rustup…")
        download(url, init_path)
        if not is_windows():
            init_path.chmod(init_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        print("        installing rustup (may take a few minutes)…")
        # Capture stdout: rustup-init prints PATH advice that does not apply under Pixi.
        result = subprocess.run(
            [
                str(init_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
                "--no-modify-path",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            _fail("rustup install failed")
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                for line in detail.splitlines()[-15:]:
                    print(f"        {line}")
            print("        Check network access to static.rust-lang.org")
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        _fail(f"rustup install failed: {e}")
        print("        Check network access to static.rust-lang.org")
        raise SystemExit(1) from e
    finally:
        if init_path.exists():
            init_path.unlink()

    if not (cargo_bin / _exe("rustup")).exists():
        _fail("rustup binary missing after install")
        raise SystemExit(1)

    return "rustup (installed)"


def install_elf2uf2() -> str:
    """ELF→UF2 only — skip default serial feature (needs libudev on Linux)."""
    result = subprocess.run(
        ["cargo", "install", "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    if "elf2uf2-rs" in result.stdout:
        return "elf2uf2-rs"

    print("        compiling elf2uf2-rs (first time only)…")
    result = subprocess.run(
        ["cargo", "install", "elf2uf2-rs", "--no-default-features", "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("elf2uf2-rs install failed")
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            for line in detail.splitlines()[-20:]:
                print(f"        {line}")
        raise SystemExit(1)
    return "elf2uf2-rs (installed)"


def _conda_bindir(conda_prefix: Path) -> Path:
    if is_windows():
        return conda_prefix / "Library" / "bin"
    return conda_prefix / "bin"


def picotool_asset_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    ver = PICOTOOL_VERSION
    if system == "Linux":
        if machine in ("aarch64", "arm64"):
            return f"picotool-{ver}-aarch64-lin.tar.gz"
        if machine in ("x86_64", "amd64"):
            return f"picotool-{ver}-x86_64-lin.tar.gz"
        raise RuntimeError(f"unsupported Linux arch for picotool: {machine}")
    if system == "Darwin":
        return f"picotool-{ver}-mac.zip"
    if system == "Windows":
        return f"picotool-{ver}-x64-win.zip"
    raise RuntimeError(f"unsupported OS for picotool: {system}")


def _picotool_works() -> bool:
    """True when ``picotool version`` runs (libs resolvable)."""
    if shutil.which("picotool") is None:
        return False
    result = subprocess.run(
        ["picotool", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def install_picotool(conda_prefix: Path) -> str:
    """Install Raspberry Pi picotool into the Pixi env (prebuilt SDK tools)."""
    if _picotool_works():
        ver = subprocess.run(
            ["picotool", "version"], capture_output=True, text=True, check=False
        )
        label = (ver.stdout or ver.stderr or "").strip().splitlines()
        first = label[0] if label else "present"
        return f"picotool ({first})"

    import tarfile
    import tempfile
    import zipfile

    asset = picotool_asset_name()
    url = (
        "https://github.com/raspberrypi/pico-sdk-tools/releases/download/"
        f"{PICOTOOL_TOOLS_TAG}/{asset}"
    )
    share = conda_prefix / "share" / "lucy-picotool"
    bindir = _conda_bindir(conda_prefix)
    bindir.mkdir(parents=True, exist_ok=True)

    print(f"        downloading {asset}…")
    with tempfile.TemporaryDirectory(prefix="lucy-picotool-") as tmp:
        archive = Path(tmp) / asset
        download(url, archive)
        extract_root = Path(tmp) / "extract"
        extract_root.mkdir()
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_root)
        else:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(extract_root)

        # Tarball layout: picotool/picotool (+ helper files).
        candidates = list(extract_root.rglob(_exe("picotool")))
        # Prefer the real binary, not a nested path that is a directory.
        binary = next((p for p in candidates if p.is_file()), None)
        if binary is None:
            _fail(f"picotool binary missing in {asset}")
            raise SystemExit(1)

        if share.exists():
            shutil.rmtree(share)
        share.mkdir(parents=True)
        # Copy the whole package directory so helper ELFs stay beside the binary.
        pkg_dir = binary.parent
        for item in pkg_dir.iterdir():
            dest = share / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    real_bin = share / _exe("picotool")
    if not real_bin.is_file():
        _fail("picotool install incomplete")
        raise SystemExit(1)
    real_bin.chmod(real_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    wrapper = bindir / _exe("picotool")
    if is_windows():
        # DLLs ship beside the exe on Windows builds — put them on PATH via share.
        shutil.copy2(real_bin, wrapper)
        for dll in share.glob("*.dll"):
            shutil.copy2(dll, bindir / dll.name)
    else:
        # Wrapper so CONDA_PREFIX/lib (libusb) is visible on NixOS / odd loaders.
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            f'PREFIX="{conda_prefix}"\n'
            'export LD_LIBRARY_PATH="${PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
            'export DYLD_LIBRARY_PATH="${PREFIX}/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"\n'
            f'exec "{real_bin}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Ensure bindir is early on PATH for this process.
    sep = ";" if is_windows() else ":"
    path = os.environ.get("PATH", "")
    prefix = str(bindir)
    if not path.startswith(prefix + sep) and path != prefix:
        os.environ["PATH"] = f"{prefix}{sep}{path}" if path else prefix

    if not _picotool_works():
        _fail("picotool installed but cannot run (libusb / libstdc++ missing?)")
        print("        Ensure Pixi feature firmware includes libusb, then re-run.")
        raise SystemExit(1)

    return f"picotool {PICOTOOL_VERSION} (installed)"


def udev_rules_present() -> Path | None:
    for path in (_ETC_UDEV, _RUN_UDEV):
        if path.is_file():
            return path
    return None


def _expected_udev_rules_text() -> str:
    """Expected udev rules body (same source as ``install_pico_usb_access``)."""
    script_dir = Path(__file__).resolve().parent
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "lucy_pico_usb", script_dir / "install_pico_usb_access.py"
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            text = mod.load_rules_text()
            return text if text.endswith("\n") else text + "\n"
    except Exception:
        pass
    path = script_dir / "udev" / "99-lucy-pico.rules"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        return text if text.endswith("\n") else text + "\n"
    return ""


def udev_rules_ok() -> tuple[bool, Path | None, str]:
    """Return (configured_ok, path_or_none, reason_if_not_ok)."""
    expected = _expected_udev_rules_text().rstrip("\n") + "\n"
    if not expected.strip():
        return False, None, "cannot load expected udev rules text"

    path = udev_rules_present()
    if path is None:
        return False, None, "udev rules not installed"

    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, path, f"cannot read {path}: {e}"

    if existing.rstrip("\n") + "\n" != expected:
        return False, path, f"udev rules outdated or mismatched at {path}"

    return True, path, ""


def configure_pico_usb_access() -> list[str]:
    """Ensure Pico USB access. Returns manual follow-ups only when misconfigured."""
    manual: list[str] = []
    script = Path(__file__).resolve().parent / "install_pico_usb_access.py"
    if not script.is_file():
        _need(f"Pico USB: missing {script.name}")
        manual.append(f"restore {script} and re-run firmware-setup")
        return manual

    if is_windows() or platform.system() == "Darwin":
        _ok(f"Pico USB: no udev on {platform.system()} (install picotool separately if needed)")
        return manual

    ok, path, reason = udev_rules_ok()
    if ok and path is not None:
        _ok(f"Pico USB udev ({path})")
        return manual

    if os.environ.get("LUCY_FIRMWARE_SETUP_SKIP_UDEV", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        _need(f"Pico USB: {reason or 'not configured'} (LUCY_FIRMWARE_SETUP_SKIP_UDEV)")
        manual.append("python scripts/install_pico_usb_access.py")
        return manual

    if not sys.stdin.isatty() and os.environ.get(
        "LUCY_FIRMWARE_SETUP_INSTALL_UDEV", ""
    ).strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        _need(f"Pico USB: {reason or 'not configured'} (non-interactive — install skipped)")
        manual.append("python scripts/install_pico_usb_access.py  # once, needs sudo")
        return manual

    print("        Pico USB: installing udev rules (may prompt for sudo)…")
    result = subprocess.run(
        [sys.executable, str(script), "--quiet"],
        check=False,
        text=True,
        capture_output=False,
    )
    if result.returncode != 0:
        _need("Pico USB udev install failed — flash may still work with sudo")
        manual.append(
            "python scripts/install_pico_usb_access.py  "
            "# or set LUCY_PIPELINE_FLASH_USE_SUDO=1"
        )
        return manual

    ok, path, reason = udev_rules_ok()
    if ok and path is not None:
        _ok(f"Pico USB udev ({path})")
        return manual

    _need(f"Pico USB: {reason or 'still not configured after install'}")
    manual.append("python scripts/install_pico_usb_access.py")
    return manual


def run_setup() -> None:
    refuse_if_root()
    conda_prefix = require_pixi_env()
    cargo_bin = configure_cargo_homes(conda_prefix)

    print("Firmware toolchain")
    print(f"  env   {conda_prefix}")

    rust_label = install_rustup(cargo_bin)
    _ok(rust_label)

    subprocess.run(["rustup", "default", "stable"], check=False, capture_output=True)

    _run_quiet(
        ["rustup", "target", "add", THUMBV6_TARGET],
        what=f"rustup target add {THUMBV6_TARGET}",
    )
    _ok(f"target {THUMBV6_TARGET}")

    elf_label = install_elf2uf2()
    _ok(elf_label)

    pico_label = install_picotool(conda_prefix)
    _ok(pico_label)

    errors = check_firmware_toolchain()
    if errors:
        for item in errors:
            _fail(item)
        print()
        _result_ko("toolchain incomplete")
        print(SETUP_HINT)
        raise SystemExit(1)

    manual = configure_pico_usb_access()

    print()
    if manual:
        _result_ok("toolchain ready; action required:")
        for step in manual:
            print(f"  → {step}")
    else:
        _result_ok("firmware toolchain ready")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lucy firmware toolchain setup / check")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify the toolchain is ready (no install); exit 0/1",
    )
    args = parser.parse_args(argv)

    if args.check:
        refuse_if_root()
        prefix = os.environ.get("CONDA_PREFIX", "").strip()
        if prefix:
            configure_cargo_homes(Path(prefix))
        sys.exit(print_check_result(check_firmware_toolchain()))

    run_setup()


if __name__ == "__main__":
    main()
