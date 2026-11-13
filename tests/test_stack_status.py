import json
from types import SimpleNamespace

import pytest

from launcher import stack_status as module
from launcher.state import _intended_running, _pkg_start_times, _pkg_stop_times


class FakeState:
    def __init__(self, core):
        self.core = core
        self.robot = SimpleNamespace(requires_pkg="so_arm101_urdf", selected=True)

    def get_by_id(self, pkg_id):
        return self.core if pkg_id == "core" else None

    def _robot_packages(self):
        return [self.robot]


@pytest.fixture(autouse=True)
def _no_pending_stop(monkeypatch):
    monkeypatch.delitem(_pkg_stop_times, "core", raising=False)


def _core(**kw):
    base = dict(id="core", pane_dead=False, ready=False, is_running=True, stage=None, readiness_timeout=150)
    return SimpleNamespace(**{**base, **kw})


def test_loading_core_reports_its_stage(tmp_path, monkeypatch):
    out = tmp_path / "status"
    monkeypatch.setenv("LUCY_STACK_STATUS_FILE", str(out))
    monkeypatch.setattr(module, "_last_written", None)
    core = _core(stage={"index": 6, "total": 8, "label": "Building robot model"})
    _intended_running.add("core")
    try:
        module.write_stack_status(FakeState(core))
    finally:
        _intended_running.discard("core")
        _pkg_start_times.pop("core", None)
    assert json.loads(out.read_text()) == {
        "robot": "so_arm101_urdf", "status": "loading", "ready": False,
        "index": 6, "total": 8, "label": "Building robot model",
    }


def test_ready_core_is_written_once(tmp_path, monkeypatch):
    out = tmp_path / "status"
    monkeypatch.setenv("LUCY_STACK_STATUS_FILE", str(out))
    monkeypatch.setattr(module, "_last_written", None)
    state = FakeState(_core(ready=True))
    module.write_stack_status(state)
    assert json.loads(out.read_text())["ready"] is True
    out.unlink()
    module.write_stack_status(state)
    assert not out.exists()
