"""Core readiness written for the control panel (relayed by the lucy_robot_select node)."""

import json
import os
import tempfile
from pathlib import Path

from .state import get_pkg_status

_last_written = None


def stack_status_file() -> Path:
    override = os.environ.get("LUCY_STACK_STATUS_FILE")
    if override:
        return Path(override)
    uid = getattr(os, "getuid", lambda: 0)()
    return Path(tempfile.gettempdir()) / f"lucy_stack_status.{uid}"


def stack_status(state) -> dict | None:
    core = state.get_by_id("core")
    if core is None:
        return None
    status = get_pkg_status(core)
    robot = next((p.requires_pkg for p in state._robot_packages() if p.selected), "")
    stage = core.stage if status == "loading" else None
    return {
        "robot": robot,
        "status": status,
        "ready": status == "running",
        "index": stage["index"] if stage else 0,
        "total": stage["total"] if stage else 0,
        "label": stage["label"] if stage else status.capitalize(),
    }


def write_stack_status(state) -> None:
    global _last_written
    status = stack_status(state)
    if status is None or status == _last_written:
        return
    try:
        stack_status_file().write_text(json.dumps(status), encoding="utf-8")
    except OSError:
        return
    _last_written = status
