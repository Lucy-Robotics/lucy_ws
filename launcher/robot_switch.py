"""Robot package switches requested by the control panel (lucy_robot_select node)."""

import os
import tempfile
from pathlib import Path


def select_request_file() -> Path:
    override = os.environ.get("LUCY_SELECT_ROBOT_FILE")
    if override:
        return Path(override)
    uid = getattr(os, "getuid", lambda: 0)()
    return Path(tempfile.gettempdir()) / f"lucy_select_robot.{uid}"


def take_robot_request(state):
    """Tick the robot the panel asked for; return it when the stack must restart."""
    path = select_request_file()
    try:
        robot = path.read_text(encoding="utf-8").strip()
        path.unlink()
    except OSError:
        return None
    pkg = next((p for p in state._robot_packages() if p.requires_pkg == robot), None)
    if pkg is None or pkg.selected:
        return None
    state._enable_with_deps(pkg)
    return pkg
