"""Tests for scripts/firmware_setup.py readiness checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "firmware_setup.py"


def _load_firmware_setup():
    spec = importlib.util.spec_from_file_location("firmware_setup_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fw():
    return _load_firmware_setup()


def test_check_reports_missing_conda_prefix(fw, monkeypatch):
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    errors = fw.check_firmware_toolchain()
    assert errors
    assert any("CONDA_PREFIX" in e for e in errors)


def test_check_reports_missing_binaries(fw, monkeypatch, tmp_path):
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with patch.object(fw.shutil, "which", return_value=None):
        errors = fw.check_firmware_toolchain()
    assert any("rustup" in e for e in errors)
    assert any("cargo" in e for e in errors)
    assert any("elf2uf2-rs" in e for e in errors)
    assert any("picotool" in e for e in errors)


def test_print_check_result_exit_codes(fw, capsys):
    assert fw.print_check_result([]) == 0
    assert "ready" in capsys.readouterr().out
    assert fw.print_check_result(["cargo not found"]) == 1
    out = capsys.readouterr().out
    assert "not ready" in out
    assert "firmware-setup" in out


def test_check_cli_exits_nonzero_when_missing(fw, monkeypatch):
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    with pytest.raises(SystemExit) as exc:
        fw.main(["--check"])
    assert exc.value.code == 1


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Windows", "AMD64", "https://win.rustup.rs/x86_64"),
        ("Windows", "x86_64", "https://win.rustup.rs/x86_64"),
        ("Windows", "ARM64", "https://win.rustup.rs/aarch64"),
        ("Windows", "aarch64", "https://win.rustup.rs/aarch64"),
        (
            "Linux",
            "x86_64",
            "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init",
        ),
        (
            "Darwin",
            "arm64",
            "https://static.rust-lang.org/rustup/dist/aarch64-apple-darwin/rustup-init",
        ),
    ],
)
def test_rustup_init_url(fw, monkeypatch, system, machine, expected):
    monkeypatch.setattr(fw.platform, "system", lambda: system)
    monkeypatch.setattr(fw.platform, "machine", lambda: machine)
    assert fw.rustup_init_url() == expected
