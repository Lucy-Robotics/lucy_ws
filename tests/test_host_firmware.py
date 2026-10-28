"""The activated hardware file chooses the host program and the device label."""

import importlib.util
from pathlib import Path

_MODULE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "lucy_ros_packages"
    / "lucy_bringup"
    / "launch"
    / "host_firmware.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("lucy_host_firmware", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bus_board_uses_the_configured_device_and_usb_ids():
    host = _load()
    targets, problems = host.host_plan(
        {
            "rp2040_so_arm": {
                "board_class": "bus_servo_only",
                "serial_id": "",
                "host": {
                    "firmware": "linux",
                    "device": "SO-ARM",
                    "usb": {"vid": "0x1a86", "pid": "0x55d3"},
                },
            }
        }
    )
    assert problems == []
    assert targets == [
        {
            "firmware": "linux",
            "node": "so_arm",
            "device": "SO-ARM",
            "vid": 0x1A86,
            "pid": 0x55D3,
        }
    ]


def test_a_bus_board_without_usb_ids_tells_the_user_to_fix_the_config():
    host = _load()
    targets, problems = host.host_plan(
        {"rp2040_so_arm": {"board_class": "bus_servo_only", "serial_id": ""}}
    )
    assert targets == []
    assert problems == [
        "This robot configuration does not name the USB device for so_arm. "
        "Fix it, then relaunch Lucy."
    ]


def test_pico_boards_keep_their_serial_and_append_it_to_the_device_label():
    host = _load()
    targets, problems = host.host_plan(
        {
            "rp2040_left_arm": {
                "serial_id": "ABC123",
                "host": {"device": "left arm Servo2040"},
            },
            "rp2040_torso_head": {"serial_id": ""},
            "rp2040_right_arm": {"serial_id": "DEF456"},
        }
    )
    assert problems == []
    assert targets == [
        {
            "firmware": "mcu_bridge",
            "node": "left_arm",
            "device": "left arm Servo2040 (ABC123)",
            "serial": "ABC123",
        },
        {
            "firmware": "mcu_bridge",
            "node": "right_arm",
            "device": "right_arm (DEF456)",
            "serial": "DEF456",
        },
    ]
