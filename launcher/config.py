"""Configuration, state persistence, and workspace environment loading."""

import json
import os

from .constants import (
    DEFAULT_CONFIG_FILE,
    LOCAL_CONFIG_FILE,
    SELECTION_FILE,
    STATE_FILE,
    WORKSPACE_ROOT,
)


def get_dev_mode():
    env_path = WORKSPACE_ROOT / ".env"
    if not os.path.exists(env_path):
        return False
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("DEV="):
                return line.strip().split("=")[1].lower() == "true"
    return False


def load_workspace_env():
    """Load optional .env into os.environ (ports, GUI overrides, DEV=)."""
    import launcher

    env_path = launcher.WORKSPACE_ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key:
                continue
            val = val.strip().strip('"').strip("'")
            os.environ[key] = val


def _launcher_config_path():
    """config/launcher_config.json.local (gitignored) overrides the tracked file."""
    return str(LOCAL_CONFIG_FILE if LOCAL_CONFIG_FILE.exists() else DEFAULT_CONFIG_FILE)


def load_config():
    config_path = _launcher_config_path()
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    with open(config_path, "r") as f:
        return json.load(f)


def load_state():
    if not STATE_FILE.is_file():
        return {"modifiers": []}
    with open(STATE_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"modifiers": []}


def save_state(state_data):
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)


def load_selection():
    """Set of package ids the user last applied, or None if never saved."""
    if not os.path.exists(SELECTION_FILE):
        return None
    try:
        with open(SELECTION_FILE) as f:
            return set(json.load(f).get("selected", []))
    except (json.JSONDecodeError, OSError):
        return None


def save_selection(selected_ids):
    """Persist the applied tick selection so it is restored on the next launch."""
    tmp = f"{SELECTION_FILE}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({"selected": sorted(selected_ids)}, f)
        # Replace, don't rewrite in place: a root-owned file left by the Docker setup
        # can't be opened for writing, but the user-owned directory lets us swap it.
        os.replace(tmp, SELECTION_FILE)
    except OSError:
        pass
