#!/usr/bin/env python3
"""Colored status lines for firmware Pixi scripts (no emoji)."""
from __future__ import annotations

import os
import sys

_RESET = "\033[0m"
# Truecolor: green / amber / red
_OK = "\033[38;2;0;255;65m"  # #00FF41
_WARN = "\033[38;2;255;176;0m"  # #FFB000
_ERR = "\033[38;2;255;51;51m"  # #FF3333
_BOLD = "\033[1m"


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def enable_ansi() -> None:
    """Enable VT processing on Windows so truecolor escapes work."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _paint(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"


def ok(msg: str) -> None:
    print(_paint(_OK, f"[ok] {msg}"))


def warn(msg: str) -> None:
    print(_paint(_WARN, f"[warn] {msg}"))


def err(msg: str) -> None:
    print(_paint(_ERR, f"[error] {msg}"), file=sys.stderr)


def info(msg: str) -> None:
    print(msg)


def step(n: int, total: int, title: str) -> None:
    label = _paint(_BOLD, f"[{n}/{total}]")
    print(f"\n{label} {title}")
