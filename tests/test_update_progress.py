import pytest

import install
import components
import update_progress
import update_watch


def _steps(*states):
    return [{"label": str(i), "state": state} for i, state in enumerate(states)]


def test_steps_move_from_next_to_done(tmp_path):
    update_progress.plan(tmp_path, ["a", "b"])
    with update_progress.step(tmp_path, "a"):
        assert [row["state"] for row in update_progress.read(tmp_path)] == ["running", "next"]
    assert [row["state"] for row in update_progress.read(tmp_path)] == ["done", "next"]


def test_a_failing_step_is_marked_and_still_raises(tmp_path):
    update_progress.plan(tmp_path, ["a"])
    with pytest.raises(RuntimeError):
        with update_progress.step(tmp_path, "a"):
            raise RuntimeError("boom")
    assert update_progress.read(tmp_path)[0]["state"] == "failed"


def test_steps_without_a_plan_write_nothing(tmp_path):
    with update_progress.step(tmp_path, "a"):
        pass
    assert not (tmp_path / "log").exists()


def test_a_torn_progress_file_reads_as_empty(tmp_path):
    update_progress.plan(tmp_path, ["a"])
    (tmp_path / update_progress.PROGRESS_FILE).write_text("{")
    assert update_progress.read(tmp_path) == []


def test_the_watch_keeps_the_running_step_and_what_comes_next_in_view():
    steps = _steps(*["done"] * 10, "running", *["next"] * 10)
    shown = update_watch.visible(steps, 5)
    assert [row["state"] for row in shown] == ["done", "done", "running", "next", "next"]


def test_the_watch_shows_the_last_steps_at_the_end():
    assert len(update_watch.visible(_steps(*["done"] * 20), 5)) == 5


def test_the_plan_lists_each_selected_repo_then_the_build_stages(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "repos.json").write_text(
        '{"repos": [{"name": "lucy_ros_packages", "branch": "dev", "url_https": "https://x/a.git"},'
        ' {"name": "marty_urdf", "branch": "dev", "url_https": "https://x/m.git"}]}')
    monkeypatch.delenv("LUCY_SKIP_FIRMWARE_SETUP", raising=False)
    assert install.flow_steps(tmp_path, "update", False, None, False) == [
        "Update lucy_ros_packages", update_progress.PIXI, update_progress.BUILD,
        update_progress.PANEL, update_progress.FIRMWARE,
    ]
    components.save(tmp_path, {**components.DEFAULTS, "robot_marty": True, "firmware": False})
    assert install.flow_steps(tmp_path, "update", False, None, True) == [
        "Update lucy_ros_packages", "Update marty_urdf", update_progress.PIXI,
    ]
