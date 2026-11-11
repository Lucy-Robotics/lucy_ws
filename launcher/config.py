"""Configuration, state persistence, and workspace environment loading."""

import json
import os

from .constants import (
    DEFAULT_CONFIG_FILE,
    INSTANCE_ENV_KEYS,
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
            # launch_lucy.sh already derived these from .env, per instance
            # (e.g. PORT_ROSBRIDGE + 1 for lucy_ws_1); keep what it passed.
            if key in INSTANCE_ENV_KEYS and key in os.environ:
                continue
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


def _load_selection_file():
    try:
        with open(SELECTION_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def load_selection():
    """Set of package ids the user last applied, or None if never saved."""
    data = _load_selection_file()
    return None if data is None else set(data.get("selected", []))


def load_selected_domain_id():
    """ROS domain id the user last applied (raw), or None if never saved."""
    data = _load_selection_file()
    return None if data is None else data.get("domain_id")


def save_selection(selected_ids, domain_id):
    """Persist the applied ticks and ROS domain so they are restored on the next launch."""
    data = {"selected": sorted(selected_ids), "domain_id": domain_id}
    tmp = f"{SELECTION_FILE}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        # Replace, don't rewrite in place: a root-owned file left by the Docker setup
        # can't be opened for writing, but the user-owned directory lets us swap it.
        os.replace(tmp, SELECTION_FILE)
    except OSError:
        pass
