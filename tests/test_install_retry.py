import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402
import install_retry  # noqa: E402


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(install_retry, "RETRY_DELAYS_S", (0, 0))


def github_refusing(times):
    commands = []

    def run(command, check=True, cwd=None):
        commands.append(command)
        if len(commands) <= times:
            raise subprocess.CalledProcessError(128, command)
        return 0

    return run, commands


def test_a_clone_refused_once_is_retried_and_installs(tmp_path):
    run, commands = github_refusing(1)
    install.fetch_repo_git("foo", "https://github.com/x/foo.git", "dev", str(tmp_path / "foo"), "install", run, lambda _: None)
    assert [c[:2] for c in commands] == [["git", "clone"], ["git", "clone"]]


def test_a_clone_that_keeps_failing_stops_after_three_attempts(tmp_path):
    run, commands = github_refusing(5)
    with pytest.raises(subprocess.CalledProcessError):
        install.fetch_repo_git("foo", "https://github.com/x/foo.git", "dev", str(tmp_path / "foo"), "install", run, lambda _: None)
    assert len(commands) == 3


def test_a_retried_clone_starts_from_an_empty_folder(tmp_path):
    dest = tmp_path / "foo"
    left_over = []

    def run(command, check=True, cwd=None):
        left_over.append(dest.exists())
        if len(left_over) == 1:
            (dest / "partial").mkdir(parents=True)
            raise subprocess.CalledProcessError(128, command)
        return 0

    install.fetch_repo_git("foo", "https://github.com/x/foo.git", "dev", str(dest), "install", run, lambda _: None)
    assert left_over == [False, False]


def test_a_refused_fetch_is_retried(tmp_path, monkeypatch):
    (tmp_path / "foo" / ".git").mkdir(parents=True)
    monkeypatch.setattr(install, "run_quiet", lambda cmd: subprocess.CompletedProcess(cmd, 0, "https://github.com/x/foo.git\n", ""))
    run, commands = github_refusing(1)
    install.fetch_repo_git("foo", "https://github.com/x/foo.git", "dev", str(tmp_path / "foo"), "install", run, lambda _: None)
    assert [c[3] for c in commands[:2]] == ["fetch", "fetch"]
