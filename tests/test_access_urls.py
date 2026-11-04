"""The panel row lists every URL it answers on, as far as the terminal is wide."""

from types import SimpleNamespace

import pytest

from launcher import access_urls as module
from launcher.access_urls import access_urls, fit_urls, reachable

LOCAL = "https://localhost:4004"
LAN = "https://10.0.0.5:4004"


def _state(command, is_running=True):
    panel = SimpleNamespace(id="control_panel", parent=None, url=LOCAL)
    option = SimpleNamespace(id="host", parent="control_panel", command=command, is_running=is_running)
    return panel, SimpleNamespace(packages=[panel, option])


@pytest.fixture(autouse=True)
def lan(monkeypatch):
    monkeypatch.setattr(module, "network_ips", lambda: ["10.0.0.5"])


def test_every_network_lists_each_address_after_localhost():
    panel, state = _state("--host 0.0.0.0")
    assert access_urls(panel, state) == [LOCAL, LAN]


@pytest.mark.parametrize("command, is_running", [("--host 127.0.0.1", True), ("--host 0.0.0.0", False)])
def test_only_the_launched_every_network_option_lists_addresses(command, is_running):
    panel, state = _state(command, is_running)
    assert access_urls(panel, state) == [LOCAL]


def test_urls_stop_at_the_terminal_edge():
    assert fit_urls([LOCAL, LAN], 100) == f" ({LOCAL}  {LAN})"
    assert fit_urls([LOCAL, LAN], 30) == f" ({LOCAL})"
    assert fit_urls([LOCAL, LAN], 5) == ""


@pytest.mark.parametrize("ip, expected", [
    ("192.168.1.20", True), ("100.85.90.5", True), ("127.0.1.1", False), ("172.17.0.1", False),
])
def test_loopback_and_container_bridges_are_not_reachable(ip, expected):
    assert reachable(ip) is expected
