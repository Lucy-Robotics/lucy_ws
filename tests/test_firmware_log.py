"""Firmware status lines go through logging, with the same colored prefixes."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from firmware_log import get_logger  # noqa: E402

_GREEN = "\033[38;2;0;255;65m"
_AMBER = "\033[38;2;255;176;0m"
_RED = "\033[38;2;255;51;51m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def test_status_lines_use_logger_levels_and_colors(monkeypatch, capfd):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    log = get_logger()
    log.ok("ready")
    log.warning("careful")
    log.error("failed")
    log.info("plain")
    log.info("100% done")
    log.step(1, 5, "Checking")

    captured = capfd.readouterr()
    assert captured.out == (
        f"{_GREEN}[ok] ready{_RESET}\n"
        f"{_AMBER}[warn] careful{_RESET}\n"
        "plain\n"
        "100% done\n"
        f"\n{_BOLD}[1/5]{_RESET} Checking\n"
    )
    assert captured.err == f"{_RED}[error] failed{_RESET}\n"


def test_no_color_strips_escapes_but_keeps_prefixes(monkeypatch, capfd):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    log = get_logger()
    log.ok("ready")
    log.warning("careful")
    log.error("failed")
    log.step(2, 5, "Install")

    captured = capfd.readouterr()
    assert captured.out == "[ok] ready\n[warn] careful\n\n[2/5] Install\n"
    assert captured.err == "[error] failed\n"
