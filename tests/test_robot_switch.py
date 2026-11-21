from types import SimpleNamespace

from launcher.robot_switch import take_robot_request


class FakeState:
    def __init__(self):
        self.robots = [
            SimpleNamespace(name="Robot: InMoov", requires_pkg="inmoov_urdf", selected=True),
            SimpleNamespace(name="Robot: SO-ARM101", requires_pkg="so_arm101_urdf", selected=False),
        ]

    def _robot_packages(self):
        return self.robots

    def _enable_with_deps(self, pkg):
        for robot in self.robots:
            robot.selected = robot is pkg


def test_panel_request_ticks_the_robot_and_is_consumed(tmp_path, monkeypatch):
    request = tmp_path / "select"
    monkeypatch.setenv("LUCY_SELECT_ROBOT_FILE", str(request))
    state = FakeState()
    request.write_text("so_arm101_urdf")
    assert take_robot_request(state).name == "Robot: SO-ARM101"
    assert [r.selected for r in state.robots] == [False, True]
    assert not request.exists()


def test_no_request_unknown_or_current_robot_changes_nothing(tmp_path, monkeypatch):
    request = tmp_path / "select"
    monkeypatch.setenv("LUCY_SELECT_ROBOT_FILE", str(request))
    state = FakeState()
    assert take_robot_request(state) is None
    for robot in ("thais_urdf", "inmoov_urdf"):
        request.write_text(robot)
        assert take_robot_request(state) is None
    assert [r.selected for r in state.robots] == [True, False]
