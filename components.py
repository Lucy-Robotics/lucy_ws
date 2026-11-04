from __future__ import annotations

from pathlib import Path

LABELS = {
    "simulation": "Simulation (Gazebo)",
    "visualisation": "Visualisation (RViz, rqt)",
    "control_panel": "Control panel (web UI)",
    "firmware": "Embedded firmware (real hardware)",
    "robot_inmoov": "Robot: InMoov",
    "robot_so_arm101": "Robot: SO-ARM101",
    "robot_inmoov_i2": "Robot: InMoov i2",
    "robot_marty": "Robot: Marty",
}
OFF_BY_DEFAULT = {"simulation", "robot_marty"}
DEFAULTS = {name: name not in OFF_BY_DEFAULT for name in LABELS}
REPOS = {
    "control_panel": "lucy_control_panel",
    "firmware": "lucy_embedded_firmware",
    "robot_inmoov": "inmoov_urdf",
    "robot_so_arm101": "so_arm101_urdf",
    "robot_inmoov_i2": "inmoov_i2_urdf",
    "robot_marty": "marty_urdf",
}
ROBOTS = [name for name in LABELS if name.startswith("robot_")]
PIXI_ENV_KEY = "LUCY_PIXI_ENV"
PIXI_ENVS = {
    (False, True): "default",
    (True, True): "sim",
    (False, False): "minimal",
    (True, False): "minimal-sim",
}
LEFT_OUT_MARK = "Left out by the Lucy component choice\n"


def env_key(name: str) -> str:
    return f"LUCY_{name.upper()}"


def _env_file(root: Path | str) -> Path:
    return Path(root) / ".env"


def _env_lines(root: Path | str) -> list[str]:
    path = _env_file(root)
    return path.read_text().splitlines() if path.is_file() else []


def load(root: Path | str) -> dict[str, bool]:
    pairs = (line.split("=", 1) for line in _env_lines(root) if "=" in line and not line.lstrip().startswith("#"))
    values = {k.strip(): v.strip().strip("'\"").lower() for k, v in pairs}
    return {
        name: values[env_key(name)] in ("1", "true", "yes") if env_key(name) in values else default
        for name, default in DEFAULTS.items()
    }


def problems(selection: dict[str, bool]) -> list[str]:
    return [] if any(selection[robot] for robot in ROBOTS) else ["Pick at least one robot"]


def pixi_env(selection: dict[str, bool]) -> str:
    return PIXI_ENVS[(selection["simulation"], selection["visualisation"])]


def save(root: Path | str, selection: dict[str, bool]) -> None:
    values = {env_key(name): str(on).lower() for name, on in selection.items()}
    values[PIXI_ENV_KEY] = pixi_env(selection)
    kept = [line for line in _env_lines(root) if line.split("=", 1)[0].strip() not in values]
    _env_file(root).write_text("\n".join(kept + [f"{k}={v}" for k, v in values.items()]) + "\n")


def pixi_command(root: Path | str, args: list[str]) -> list[str]:
    if args and args[0] in ("run", "install"):
        return ["pixi", args[0], "-e", pixi_env(load(root)), *args[1:]]
    return ["pixi", *args]


def left_out_repos(selection: dict[str, bool]) -> set[str]:
    return {repo for name, repo in REPOS.items() if not selection[name]}


def _left_out_mark(repo_dir: Path) -> bool:
    ignore = repo_dir / "COLCON_IGNORE"
    return ignore.is_file() and ignore.read_text() == LEFT_OUT_MARK


def mark_left_out(root: Path | str, selection: dict[str, bool]) -> list[str]:
    left_out = left_out_repos(selection)
    marked = []
    for repo in REPOS.values():
        repo_dir = Path(root) / "src" / repo
        ignore = repo_dir / "COLCON_IGNORE"
        if repo in left_out and repo_dir.is_dir():
            ignore.write_text(LEFT_OUT_MARK)
            marked.append(repo)
        elif _left_out_mark(repo_dir):
            ignore.unlink()
    return marked


def installed(root: Path | str, name: str) -> bool:
    root = Path(root)
    if name not in REPOS:
        saved = load(root)
        return saved[name] and (root / ".pixi" / "envs" / pixi_env(saved)).is_dir()
    repo_dir = root / "src" / REPOS[name]
    built = name not in ROBOTS or (root / "install" / REPOS[name]).is_dir()
    return repo_dir.is_dir() and built and not _left_out_mark(repo_dir)


def summary(selection: dict[str, bool]) -> str:
    return ", ".join(f"{LABELS[name]}: {'on' if on else 'off'}" for name, on in selection.items())
