"""Tests for how install.py surfaces the progress of a long install."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402


def test_run_command_leaves_child_stdio_inherited(monkeypatch):
    """Capturing a child would hide git/ssh passphrase and host-key prompts,
    and would stop git and pixi reporting their own progress."""
    seen = {}

    def fake_run(command, cwd=None, check=False, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    install.default_run_command(["git", "clone", "x", "y"])

    assert not {"stdout", "stderr", "stdin"} & set(seen)


def test_run_command_streams_child_output_live(capfd):
    install.default_run_command([sys.executable, "-c", "print('live output')"])
    assert "live output" in capfd.readouterr().out


def test_run_command_announcement_is_flushed(capfd):
    """The announcement flushes the whole stdout buffer, so log lines written
    before it stay in order ahead of the child's output when piped."""
    install.default_run_command([sys.executable, "-c", "pass"])
    assert "--- Running:" in capfd.readouterr().out


def test_clone_does_not_force_progress():
    """--progress only takes effect off a TTY, where its \\r frames garble
    line-based consumers such as Lucy-Setup.exe. git covers the TTY case."""
    commands = []

    def record(command, check=True, cwd=None):
        commands.append(command)
        return 0

    install.fetch_repo_git("foo", "git@example.com:foo.git", "dev", "/nonexistent/foo",
                           "install", record, lambda _msg: None)

    assert commands == [["git", "clone", "-b", "dev",
                         "git@example.com:foo.git", "/nonexistent/foo"]]


def test_setup_firmware_toolchain_skips_when_env_set(monkeypatch):
    calls = []

    def fake_pixi_run(project_root, args, run_command):
        calls.append(args)
        return 0

    monkeypatch.setenv("LUCY_SKIP_FIRMWARE_SETUP", "1")
    monkeypatch.setattr(install, "pixi_run", fake_pixi_run)
    install.setup_firmware_toolchain("/tmp/ws", lambda *a, **k: 0, log=lambda m: None)
    assert calls == []


def test_setup_firmware_toolchain_runs_pixi_task(monkeypatch):
    calls = []

    def fake_pixi_run(project_root, args, run_command):
        calls.append(list(args))
        return 0

    monkeypatch.delenv("LUCY_SKIP_FIRMWARE_SETUP", raising=False)
    monkeypatch.setattr(install, "pixi_run", fake_pixi_run)
    install.setup_firmware_toolchain("/tmp/ws", lambda *a, **k: 0, log=lambda m: None)
    assert calls == [["run", "firmware-setup"]]
