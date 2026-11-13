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


def _udev_dirs(monkeypatch, tmp_path, installed: str | None):
    src = tmp_path / "src"
    dest = tmp_path / "etc"
    src.mkdir()
    dest.mkdir()
    (src / "99-lucy.rules").write_text("RULE\n")
    if installed is not None:
        (dest / "99-lucy.rules").write_text(installed)
    monkeypatch.setattr(usb, "UDEV_SOURCE_DIR", src)
    monkeypatch.setattr(usb, "UDEV_TARGET_DIR", dest)
    monkeypatch.setattr(usb, "OBSOLETE_RULE", dest / "99-lucy-rp2040.rules")


def test_udev_rules_installed_only_when_identical(monkeypatch, tmp_path):
    _udev_dirs(monkeypatch, tmp_path, installed="RULE\n")
    assert usb.udev_rules_installed()
    (tmp_path / "etc" / "99-lucy.rules").write_text("OLD RULE\n")
    assert not usb.udev_rules_installed()
    (tmp_path / "etc" / "99-lucy.rules").unlink()
    assert not usb.udev_rules_installed()


def test_ensure_usb_access_skips_sudo_when_rules_installed(monkeypatch, tmp_path):
    _udev_dirs(monkeypatch, tmp_path, installed="RULE\n")
    monkeypatch.delenv("LUCY_SKIP_USB_ACCESS", raising=False)
    monkeypatch.setattr(usb.platform, "system", lambda: "Linux")
    monkeypatch.setattr(usb, "matching_tty_nodes", lambda: [])
    sudo = MagicMock()
    monkeypatch.setattr(usb, "_sudo", sudo)
    monkeypatch.setattr(usb, "_sudo_available_noninteractive", sudo)
    usb.ensure_usb_access(allow_prompt=True)
    sudo.assert_not_called()
