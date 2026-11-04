"""Workspace paths, timeouts, and markers for the Lucy launcher."""

import os
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = WORKSPACE_ROOT / "config"
DEFAULT_CONFIG_FILE = CONFIG_DIR / "launcher_config.json"
LOCAL_CONFIG_FILE = CONFIG_DIR / "launcher_config.json.local"
STATE_FILE = WORKSPACE_ROOT / ".lucy_launcher_modifiers.json"
OPTIONS_FILE = WORKSPACE_ROOT / ".lucy_launcher_options.json"
SELECTION_FILE = WORKSPACE_ROOT / ".lucy_launcher_state.json"
LAUNCHER_PIDFILE = WORKSPACE_ROOT / ".lucy_launcher.pid"
TMUX_SESSION = os.environ.get("LUCY_TMUX_SESSION", "lucy_ws")
MIN_TERM_HEIGHT = 22
MIN_TERM_WIDTH = 65

LOADING_TIMEOUT = 30  # seconds before LOADING transitions to CRASHED
STOPPING_TIMEOUT = 30  # seconds to show STOPPING before giving up
REDRAW_INTERVAL_MS = 250  # TUI repaint tick while any package is live
ROS_LOG_RETENTION_DAYS = 7  # older ros2 launch log dirs are pruned on exit

LUCY_WS_MARKER = str(WORKSPACE_ROOT)


def _norm_path(s: str) -> str:
    return s.replace("\\", "/")


PIXI_ENV_MARKER = f"{_norm_path(LUCY_WS_MARKER)}/.pixi/"
CONTROL_PANEL_DIR = f"{_norm_path(LUCY_WS_MARKER)}/src/lucy_control_panel"
ORPHAN_CLEANUP_DEBOUNCE = 1.5

NIX_GL_ENV_SCRIPT = WORKSPACE_ROOT / "scripts" / "nix_gl_env.sh"
DDS_ENV_SCRIPT = WORKSPACE_ROOT / "scripts" / "dds_env.sh"

# Forward into tmux panes — GUI processes do not inherit the launcher session env.
GUI_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "QT_QPA_PLATFORM",
    "QT_XCB_GL_INTEGRATION",
    "LIBGL_ALWAYS_SOFTWARE",
    "MESA_LOADER_DRIVER_OVERRIDE",
    "LIBGL_DRIVERS_PATH",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "__EGL_VENDOR_LIBRARY_FILENAMES",
    "__GLX_VENDOR_LIBRARY_NAME",
    "GZ_IP",
    "LUCY_GPU_MODE",
    "LUCY_HEADLESS_RUNTIME_DIR",
    "GZ_RENDERING_PLUGIN_PATH",
    "GZ_RENDERING_RESOURCE_PATH",
)

# Back-compat aliases used by tests and internal modules.
_PIXI_ENV_MARKER = PIXI_ENV_MARKER
_CONTROL_PANEL_DIR = CONTROL_PANEL_DIR
_ORPHAN_CLEANUP_DEBOUNCE = ORPHAN_CLEANUP_DEBOUNCE
_GUI_ENV_KEYS = GUI_ENV_KEYS
