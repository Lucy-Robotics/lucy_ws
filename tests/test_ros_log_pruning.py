"""ros2 writes a log dir per launch and a file per node, and never prunes."""

import os
import sys
import time

import pytest

from launcher import prune_ros_logs


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_old_entries_are_removed(tmp_path):
    old_dir = tmp_path / "2026-01-01-00-00-00-000000-host-1"
    old_dir.mkdir()
    (old_dir / "launch.log").write_text("x")
    _age(old_dir, 30)
    old_file = tmp_path / "node_1_1.log"
    old_file.write_text("x")
    _age(old_file, 30)

    assert prune_ros_logs(retention_days=7, root=tmp_path) == 2
    assert not old_dir.exists() and not old_file.exists()


def test_recent_entries_are_kept(tmp_path):
    recent = tmp_path / "2026-09-02-00-00-00-000000-host-1"
    recent.mkdir()
    _age(recent, 1)
    assert prune_ros_logs(retention_days=7, root=tmp_path) == 0
    assert recent.exists()


@pytest.mark.skipif(
    sys.platform == "win32", reason="os.utime(follow_symlinks=False) is POSIX-only"
)
def test_latest_symlink_is_left_alone(tmp_path):
    target = tmp_path / "run"
    target.mkdir()
    link = tmp_path / "latest"
    link.symlink_to(target)
    _age(target, 30)
    os.utime(
        link,
        (time.time() - 30 * 86400, time.time() - 30 * 86400),
        follow_symlinks=False,
    )

    prune_ros_logs(retention_days=7, root=tmp_path)
    assert link.is_symlink(), "ros2's latest pointer must survive"


def test_retention_of_zero_disables_pruning(tmp_path):
    d = tmp_path / "old"
    d.mkdir()
    _age(d, 999)
    assert prune_ros_logs(retention_days=0, root=tmp_path) == 0
    assert d.exists()


def test_missing_log_dir_is_not_an_error(tmp_path):
    assert prune_ros_logs(retention_days=7, root=tmp_path / "nope") == 0


def test_pruning_runs_on_workspace_exit():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "launcher" / "__main__.py").read_text()
    assert "prune_ros_logs()" in src
    assert src.index("stop_all_packages(state)") < src.index("prune_ros_logs()")
