"""Tests for install.py's tmux bootstrap (pixi global, never over an existing tmux)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

PIXI_TMUX = "/home/user/.pixi/bin/tmux"


@pytest.fixture
def posix(monkeypatch):
    """Linux host, clean install env flags, no real PATH changes."""
    monkeypatch.setattr(install.sys, "platform", "linux")
    monkeypatch.setattr(install, "prepend_pixi_to_path", lambda: None)
    for name in ("CI", "LUCY_TMUX_AUTO_INSTALL", "LUCY_SKIP_TMUX_INSTALL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def fake_which(monkeypatch, results):
    """shutil.which('tmux') returns the next value of results on each call."""
    values = iter(results)
    monkeypatch.setattr(install.shutil, "which", lambda name: next(values) if name == "tmux" else None)


def recorder(returncode=0):
    commands = []

    def run(command, check=True, cwd=None):
        commands.append(command)
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, command)
        return returncode

    return commands, run


def test_existing_tmux_is_left_alone(posix):
    fake_which(posix, ["/usr/bin/tmux"])
    commands, run = recorder()

    assert install.ensure_tmux(run, lambda _m: None) is None
    assert commands == []


def test_windows_never_installs_tmux(posix):
    posix.setattr(install.sys, "platform", "win32")
    fake_which(posix, [None])
    commands, run = recorder()

    assert install.ensure_tmux(run, lambda _m: None) is None
    assert commands == []


def test_missing_tmux_is_installed_with_pixi_global(posix):
    posix.setenv("LUCY_TMUX_AUTO_INSTALL", "1")
    fake_which(posix, [None, PIXI_TMUX])
    commands, run = recorder()

    assert install.ensure_tmux(run, lambda _m: None) is None
    assert commands == [["pixi", "global", "install", "tmux"]]


def test_skip_flag_warns_without_installing(posix):
    posix.setenv("LUCY_SKIP_TMUX_INSTALL", "1")
    fake_which(posix, [None])
    commands, run = recorder()

    warning = install.ensure_tmux(run, lambda _m: None)
    assert commands == []
    assert "pixi global install tmux" in warning


def test_declined_prompt_warns(posix):
    fake_which(posix, [None])
    posix.setattr(install, "confirm_install", lambda *a, **k: False)
    commands, run = recorder()

    assert "declined" in install.ensure_tmux(run, lambda _m: None)
    assert commands == []


def test_non_interactive_without_opt_in_warns_instead_of_failing(posix):
    """The build is still worth finishing: tmux is only needed to launch."""
    fake_which(posix, [None])
    posix.setattr(install.sys, "stdin", None)
    commands, run = recorder()

    warning = install.ensure_tmux(run, lambda _m: None)
    assert "LUCY_TMUX_AUTO_INSTALL=1" in warning
    assert commands == []


def test_failed_install_warns(posix):
    posix.setenv("LUCY_TMUX_AUTO_INSTALL", "1")
    fake_which(posix, [None])
    _, run = recorder(returncode=1)

    assert "failed" in install.ensure_tmux(run, lambda _m: None)


def test_install_that_leaves_tmux_off_path_warns(posix):
    posix.setenv("LUCY_TMUX_AUTO_INSTALL", "1")
    fake_which(posix, [None, None])
    _, run = recorder()

    assert "not on PATH" in install.ensure_tmux(run, lambda _m: None)


def test_macos_hint_mentions_brew(posix):
    posix.setattr(install.sys, "platform", "darwin")
    assert "brew install tmux" in install.tmux_manual_hint()
