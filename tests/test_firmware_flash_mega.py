"""Unit tests for the Arduino Mega flash helper's port matching (no hardware required)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.firmware_flash_mega as mega  # noqa: E402


def _ports(monkeypatch, *ports):
    monkeypatch.setattr(mega.list_ports, "comports", lambda: [SimpleNamespace(**p) for p in ports])


MEGA_A = {"device": "/dev/ttyACM0", "vid": 0x2341, "pid": 0x0042, "serial_number": "AAA"}
MEGA_B = {"device": "/dev/ttyACM1", "vid": 0x2341, "pid": 0x0042, "serial_number": "BBB"}
PICO = {"device": "/dev/ttyACM2", "vid": 0x2E8A, "pid": 0x0003, "serial_number": "BBB"}


def test_serial_id_picks_its_mega_among_several(monkeypatch):
    _ports(monkeypatch, MEGA_A, PICO, MEGA_B)
    assert mega.find_port("BBB") == "/dev/ttyACM1"


def test_empty_serial_id_uses_the_only_mega(monkeypatch):
    _ports(monkeypatch, PICO, MEGA_A)
    assert mega.find_port("") == "/dev/ttyACM0"


def test_empty_serial_id_refuses_to_guess_between_megas(monkeypatch):
    _ports(monkeypatch, MEGA_A, MEGA_B)
    with pytest.raises(SystemExit, match="2 Megas"):
        mega.find_port("")


def test_unknown_serial_id_lists_what_is_plugged(monkeypatch):
    _ports(monkeypatch, MEGA_A)
    with pytest.raises(SystemExit, match="ttyACM0=AAA"):
        mega.find_port("ZZZ")
