"""Unit tests for Lucy USB-serial access helpers (no hardware required)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.firmware_usb_access as usb  # noqa: E402


def test_lucy_usb_ids_cover_pico_and_feetech():
    ids = {(v, p) for v, p, _ in usb.LUCY_USB_IDS}
    assert ("2e8a", "0003") in ids
    assert ("1a86", "55d3") in ids


def test_ensure_usb_access_skips_when_env_set(monkeypatch, capsys):
    monkeypatch.setenv("LUCY_SKIP_USB_ACCESS", "1")
    usb.ensure_usb_access(allow_prompt=False)
    assert "LUCY_SKIP_USB_ACCESS" in capsys.readouterr().out


def test_ensure_usb_access_skips_non_linux(monkeypatch, capsys):
    monkeypatch.delenv("LUCY_SKIP_USB_ACCESS", raising=False)
    monkeypatch.setattr(usb.platform, "system", lambda: "Darwin")
    usb.ensure_usb_access(allow_prompt=False)
    assert "not Linux" in capsys.readouterr().out


def test_matching_tty_nodes_filters_by_vid_pid(monkeypatch, tmp_path):
    acm = tmp_path / "ttyACM0"
    acm.write_text("")
    other = tmp_path / "ttyACM1"
    other.write_text("")

    def fake_glob(self, pattern):
        if self == Path("/dev") and pattern == "ttyACM*":
            return [acm, other]
        return []

    def fake_ids(node: Path):
        if node == acm:
            return ("1a86", "55d3")
        return ("0000", "0000")

    monkeypatch.setattr(Path, "glob", fake_glob)
    monkeypatch.setattr(usb, "tty_usb_ids", fake_ids)
    found = usb.matching_tty_nodes()
    assert len(found) == 1
    assert found[0][0] == acm
    assert "Feetech" in found[0][3]


def test_apply_temporary_access_chmods_when_needed(monkeypatch, tmp_path):
    node = tmp_path / "ttyACM0"
    node.write_text("")
    monkeypatch.setattr(
        usb,
        "matching_tty_nodes",
        lambda: [(node, "1a86", "55d3", "Feetech")],
    )
    monkeypatch.setattr(usb.os, "access", lambda *a, **k: False)
    chmod = MagicMock()
    monkeypatch.setattr(usb.os, "chmod", chmod)
    fixed = usb.apply_temporary_access(allow_prompt=False)
    assert fixed == [node]
    chmod.assert_called_once_with(node, 0o666)
