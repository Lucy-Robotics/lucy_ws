import pytest

from launcher.choices import settle_selection


@pytest.fixture
def state(isolated_state):
    return isolated_state


def _on(state):
    return {p.id for p in state.packages if p.selected}


def _launch_args(state):
    return " ".join(
        p.command
        for p in state.packages
        if p.type == "modifier" and p.selected and not p.requires_pkg and p.command
    )


def test_ticking_core_ticks_simulator(state):
    state.toggle("core")
    assert "simulator" in _on(state)
    assert not _on(state) & {"gazebo", "hardware", "real_linux", "real_mcu_bridge"}


def test_ticking_hardware_ticks_micro_controllers(state):
    state.toggle("core")
    state.toggle("hardware")
    assert {"hardware", "real_mcu_bridge"} <= _on(state)
    assert "simulator" not in _on(state)


def test_ticking_usb_servos_switches_hardware_type(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    assert "real_linux" in _on(state)
    assert "real_mcu_bridge" not in _on(state)


def test_unticking_default_simulator_is_refused(state):
    state.toggle("core")
    assert state.toggle("simulator") == "One launch mode required"
    assert state.get_by_id("simulator").selected


def test_unticking_default_micro_controllers_is_refused(state):
    state.toggle("core")
    state.toggle("hardware")
    assert state.toggle("real_mcu_bridge") == "One hardware type required"
    assert state.get_by_id("real_mcu_bridge").selected


def test_unticking_physics_simulator_ticks_simulator_and_clears_headless(state):
    state.toggle("core")
    state.toggle("gazebo")
    state.toggle("headless")
    assert state.toggle("gazebo") is None
    assert "simulator" in _on(state)
    assert not _on(state) & {"gazebo", "headless"}


def test_unticking_hardware_ticks_simulator_and_clears_bridge(state):
    state.toggle("core")
    state.toggle("hardware")
    assert state.toggle("hardware") is None
    assert "simulator" in _on(state)
    assert not _on(state) & {"hardware", "real_mcu_bridge"}


def test_unticking_usb_servos_ticks_micro_controllers(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    assert state.toggle("real_linux") is None
    assert {"hardware", "real_mcu_bridge"} <= _on(state)
    assert "real_linux" not in _on(state)


def test_switching_to_hardware_unticks_headless(state):
    state.toggle("core")
    state.toggle("gazebo")
    state.toggle("headless")
    assert "headless" in _on(state)
    state.toggle("hardware")
    assert not _on(state) & {"gazebo", "headless"}


def test_ticking_hardware_type_in_simulator_selects_hardware(state):
    state.toggle("core")
    state.toggle("real_linux")
    assert {"hardware", "real_linux"} <= _on(state)
    assert "simulator" not in _on(state)


def test_settle_drops_bridge_without_hardware_and_picks_simulator(state):
    for pkg_id in ("core", "real_linux"):
        state.get_by_id(pkg_id).selected = True
    settle_selection(state)
    assert "real_linux" not in _on(state)
    assert "simulator" in _on(state)


def _core_off_with_hardware(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    state.toggle("rviz")
    state.toggle("lucy_cli")
    state.toggle("core")


def test_unticking_core_keeps_mode_bridge_and_rviz_ticked(state):
    _core_off_with_hardware(state)
    assert "core" not in _on(state)
    assert {"hardware", "real_linux", "rviz"} <= _on(state)


def test_unticking_core_keeps_the_ticked_robot(state):
    state.toggle("core")
    state.toggle("robot_so_arm101")
    state.toggle("core")
    assert "robot_so_arm101" in _on(state)
    assert "robot_inmoov" not in _on(state)


def test_unticking_core_still_unticks_interfaces_and_tools_that_need_it(state):
    state.toggle("core")
    state.toggle("lucy_cli")
    state.toggle("rqt")
    state.toggle("core")
    assert not _on(state) & {"lucy_cli", "rqt"}


def test_reticking_core_restores_the_previous_mode_and_bridge(state):
    _core_off_with_hardware(state)
    state.toggle("core")
    assert {"core", "hardware", "real_linux", "rviz"} <= _on(state)
    assert not _on(state) & {"simulator", "real_mcu_bridge"}


def test_settle_still_drops_headless_without_gazebo_while_core_is_off(state):
    state.toggle("core")
    state.toggle("core")
    state.get_by_id("headless").selected = True
    settle_selection(state)
    assert "headless" not in _on(state)


def test_hardware_usb_servos_launch_arguments(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    assert _launch_args(state) == "mode:=real bridge:=linux"


def test_default_launch_arguments(state):
    state.toggle("core")
    assert _launch_args(state) == "mode:=mock"


def test_physics_headless_launch_arguments(state):
    state.toggle("core")
    state.toggle("gazebo")
    state.toggle("headless")
    assert _launch_args(state) == "mode:=sim headless:=true"


def test_enabling_hardware_unticks_headless_without_settling(state):
    for pkg_id in ("core", "gazebo", "headless"):
        state.get_by_id(pkg_id).selected = True
    state._enable(state.get_by_id("hardware"))
    assert not state.get_by_id("headless").selected
