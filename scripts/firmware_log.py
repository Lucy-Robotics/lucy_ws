#!/usr/bin/env python3
"""Colored status lines for the firmware scripts, via the logging library."""
from __future__ import annotations

import logging
import os
import sys

# Between INFO and WARNING, so success lines stay distinct from plain info.
OK_LEVEL = 25
logging.addLevelName(OK_LEVEL, "OK")

_RESET = "\033[0m"
# Truecolor: green / amber / red
_GREEN = "\033[38;2;0;255;65m"  # #00FF41
_AMBER = "\033[38;2;255;176;0m"  # #FFB000
_RED = "\033[38;2;255;51;51m"  # #FF3333
_BOLD = "\033[1m"

_LOGGER_NAME = "firmware"


def _use_color(stream: object) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


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


class FirmwareLogger(logging.Logger):
    def ok(self, msg: str, *args, **kwargs) -> None:
        if self.isEnabledFor(OK_LEVEL):
            self._log(OK_LEVEL, msg, args, **kwargs)

    def step(self, n: int, total: int, title: str, *args, **kwargs) -> None:
        extra = dict(kwargs.pop("extra", None) or {})
        extra["step_n"] = n
        extra["step_total"] = total
        self.info(title, *args, extra=extra, **kwargs)


class ColorFormatter(logging.Formatter):
    def __init__(self, stream_name: str) -> None:
        super().__init__()
        self._stream_name = stream_name

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        step_n = getattr(record, "step_n", None)
        step_total = getattr(record, "step_total", None)
        if step_n is not None and step_total is not None:
            label = f"[{step_n}/{step_total}]"
            if _use_color(getattr(sys, self._stream_name)):
                label = f"{_BOLD}{label}{_RESET}"
            return f"\n{label} {message}"

        if record.levelno >= logging.ERROR:
            text = f"[error] {message}"
            color = _RED
        elif record.levelno >= logging.WARNING:
            text = f"[warn] {message}"
            color = _AMBER
        elif record.levelno == OK_LEVEL:
            text = f"[ok] {message}"
            color = _GREEN
        else:
            return message

        stream = getattr(sys, self._stream_name)
        if not _use_color(stream):
            return text
        return f"{color}{text}{_RESET}"


class _BelowError(logging.Filter):
    def __init__(self) -> None:
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.ERROR


class _CurrentStreamHandler(logging.StreamHandler):
    """Write to sys.stdout or sys.stderr when the record is emitted."""

    def __init__(self, stream_name: str) -> None:
        self._stream_name = stream_name
        super().__init__(getattr(sys, stream_name))

    @property
    def stream(self):
        return getattr(sys, self._stream_name)

    @stream.setter
    def stream(self, value) -> None:
        return


def get_logger() -> FirmwareLogger:
    previous = logging.getLoggerClass()
    logging.setLoggerClass(FirmwareLogger)
    try:
        logger = logging.getLogger(_LOGGER_NAME)
    finally:
        logging.setLoggerClass(previous)

    if not isinstance(logger, FirmwareLogger):
        raise TypeError(f"logger {_LOGGER_NAME!r} is {type(logger).__name__}, not FirmwareLogger")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    stdout = _CurrentStreamHandler("stdout")
    stdout.setLevel(logging.INFO)
    stdout.addFilter(_BelowError())
    stdout.setFormatter(ColorFormatter("stdout"))

    stderr = _CurrentStreamHandler("stderr")
    stderr.setLevel(logging.ERROR)
    stderr.setFormatter(ColorFormatter("stderr"))

    logger.addHandler(stdout)
    logger.addHandler(stderr)
    return logger
