"""Tests for Jetson platform detection (Python API + bash wrapper)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from launcher.platform import (
    ensure_headless_runtime_dir,
    headless_runtime_dir,
    is_jetson,
)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DETECT_JETSON_SH = WORKSPACE_ROOT / "scripts" / "detect_jetson.sh"

# On Windows "bash" resolves to System32ash.exe (the WSL launcher), which
# exits 1 with no distro installed and never runs the script.
posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only shell helper"
)


def _run_detect_jetson(env: dict | None = None) -> int:
    script = (
        f"source {DETECT_JETSON_SH}; " "if lucy_is_jetson; then exit 0; else exit 1; fi"
    )
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=WORKSPACE_ROOT,
        env=merged,
        check=False,
    ).returncode


def test_is_jetson_respects_explicit_mode(monkeypatch):
    monkeypatch.delenv("LUCY_GPU_MODE", raising=False)
    monkeypatch.setattr(
        "launcher.platform.Path.is_file",
        lambda self: False,
    )
    monkeypatch.setenv("LUCY_GPU_MODE", "jetson")
    assert is_jetson() is True
    monkeypatch.setenv("LUCY_GPU_MODE", "0")
    assert is_jetson() is False


def test_is_jetson_does_not_treat_nvidia_as_jetson(monkeypatch):
    monkeypatch.setenv("LUCY_GPU_MODE", "nvidia")
    monkeypatch.setattr(
        "launcher.platform.Path.is_file",
        lambda self: False,
    )
    monkeypatch.setattr(
        "launcher.platform.Path.read_text",
        lambda self, **kwargs: (_ for _ in ()).throw(OSError("mock")),
    )
    assert is_jetson() is False


def test_is_jetson_from_tegra_release(monkeypatch, tmp_path):
    monkeypatch.delenv("LUCY_GPU_MODE", raising=False)

    def fake_is_file(self):
        return self.as_posix() == "/etc/nv_tegra_release"

    monkeypatch.setattr("launcher.platform.Path.is_file", fake_is_file)
    assert is_jetson() is True


def test_headless_runtime_dir_override(monkeypatch):
    monkeypatch.setenv("LUCY_HEADLESS_RUNTIME_DIR", "/tmp/lucy-test-runtime")
    assert headless_runtime_dir() == "/tmp/lucy-test-runtime"


def test_ensure_headless_runtime_dir_creates_private_dir(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LUCY_HEADLESS_RUNTIME_DIR", str(runtime))
    created = ensure_headless_runtime_dir()
    assert created == str(runtime)
    assert runtime.is_dir()
    if sys.platform != "win32":
        assert oct(runtime.stat().st_mode & 0o777) == oct(0o700)


@posix_only
def test_shell_detect_jetson_matches_python_for_jetson_mode():
    assert _run_detect_jetson({"LUCY_GPU_MODE": "jetson"}) == 0


@posix_only
@pytest.mark.skipif(not DETECT_JETSON_SH.is_file(), reason="detect_jetson.sh missing")
def test_shell_detect_jetson_rejects_disabled_mode():
    assert _run_detect_jetson({"LUCY_GPU_MODE": "0"}) != 0
