from __future__ import annotations

from pathlib import Path

DEFAULTS = {"simulation": False, "visualisation": True, "control_panel": True}
ENV_KEYS = {
    "simulation": "LUCY_SIMULATION",
    "visualisation": "LUCY_VISUALISATION",
    "control_panel": "LUCY_CONTROL_PANEL",
}
LABELS = {
    "simulation": "Simulation (Gazebo)",
    "visualisation": "Visualisation (RViz, rqt)",
    "control_panel": "Control panel (web UI)",
}
PIXI_ENV_KEY = "LUCY_PIXI_ENV"
PIXI_ENVS = {
    (False, True): "default",
    (True, True): "sim",
    (False, False): "minimal",
    (True, False): "minimal-sim",
}
CONTROL_PANEL_REPO = "lucy_control_panel"


def _env_file(root: Path | str) -> Path:
    return Path(root) / ".env"


def _env_lines(root: Path | str) -> list[str]:
    path = _env_file(root)
    return path.read_text().splitlines() if path.is_file() else []


def load(root: Path | str) -> dict[str, bool]:
    values = dict(line.split("=", 1) for line in _env_lines(root) if "=" in line and not line.lstrip().startswith("#"))
    values = {k.strip(): v.strip().strip("'\"").lower() for k, v in values.items()}
    return {
        name: values[key] in ("1", "true", "yes") if key in values else DEFAULTS[name]
        for name, key in ENV_KEYS.items()
    }


def pixi_env(selection: dict[str, bool]) -> str:
    return PIXI_ENVS[(selection["simulation"], selection["visualisation"])]


def save(root: Path | str, selection: dict[str, bool]) -> None:
    values = {ENV_KEYS[name]: str(on).lower() for name, on in selection.items()}
    values[PIXI_ENV_KEY] = pixi_env(selection)
    kept = [line for line in _env_lines(root) if line.split("=", 1)[0].strip() not in values]
    _env_file(root).write_text("\n".join(kept + [f"{k}={v}" for k, v in values.items()]) + "\n")


def pixi_command(root: Path | str, args: list[str]) -> list[str]:
    if args and args[0] in ("run", "install"):
        return ["pixi", args[0], "-e", pixi_env(load(root)), *args[1:]]
    return ["pixi", *args]


def summary(selection: dict[str, bool]) -> str:
    return ", ".join(f"{LABELS[name]}: {'on' if on else 'off'}" for name, on in selection.items())
