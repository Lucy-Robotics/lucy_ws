from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

PROGRESS_FILE = "log/update_progress.json"
PIXI = "Pixi environment"
BUILD = "Build ROS packages"
PANEL = "Control panel"
FIRMWARE = "Firmware"


def repo_step(repo: str) -> str:
    return f"Update {repo}"


def _write(path: Path, steps: list[dict]) -> None:
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(steps))
    scratch.replace(path)


def plan(root, labels: list[str]) -> None:
    path = Path(root) / PROGRESS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, [{"label": label, "state": "next"} for label in labels])


def read(root) -> list[dict]:
    try:
        return json.loads((Path(root) / PROGRESS_FILE).read_text())
    except (OSError, ValueError):
        return []


def _mark(root, label: str, state: str) -> None:
    steps = read(root)
    for step_row in steps:
        if step_row["label"] == label:
            step_row["state"] = state
    if steps:
        _write(Path(root) / PROGRESS_FILE, steps)


@contextmanager
def step(root, label: str):
    _mark(root, label, "running")
    try:
        yield
    except Exception:
        _mark(root, label, "failed")
        raise
    _mark(root, label, "done")
