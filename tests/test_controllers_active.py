"""controllers_active.sh fast path: the supervisor's ready marker."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "controllers_active.sh"
SESSION = "lucy_test_session"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="needs bash")


def _cache(tmp_path: Path) -> Path:
    return tmp_path / f"lucy_controllers_active.{os.getuid()}.{SESSION}.cache"


def _run(tmp_path: Path, marker: Path, min_active: int, **extra):
    env = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "LUCY_TMUX_SESSION": SESSION,
        "LUCY_CONTROL_READY_FILE": str(marker),
        **extra,
    }
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), str(min_active)], env=env, timeout=5, check=False
    ).returncode


def _live_marker(tmp_path: Path, count: int = 3) -> Path:
    marker = tmp_path / "ready"
    marker.write_text(f"{os.getpid()} {count}\n")
    return marker


def test_min_zero_passes_and_keeps_marker(tmp_path):
    marker = _live_marker(tmp_path)
    assert _run(tmp_path, marker, 0) == 0
    assert marker.exists()
    assert not _cache(tmp_path).exists()


def test_failing_verdict_exits_1_and_keeps_marker(tmp_path):
    marker = _live_marker(tmp_path)
    assert _run(tmp_path, marker, 4) == 1
    assert marker.exists()
    assert not _cache(tmp_path).exists()


def test_passing_min_one_deletes_marker_and_seeds_cache(tmp_path):
    marker = _live_marker(tmp_path)
    assert _run(tmp_path, marker, 1) == 0
    assert not marker.exists()
    stamp, count = _cache(tmp_path).read_text().split()
    assert stamp.isdigit()
    assert count == "3"


def test_dead_pid_marker_falls_through_to_failing_slow_path(tmp_path):
    dead = subprocess.Popen(["true"])
    dead.wait()
    marker = tmp_path / "ready"
    marker.write_text(f"{dead.pid} 3\n")
    rc = _run(tmp_path, marker, 1, PATH="/nonexistent", HOME=str(tmp_path))
    assert rc == 1
    assert marker.exists()
    assert not _cache(tmp_path).exists()
