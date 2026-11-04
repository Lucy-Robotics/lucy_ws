from __future__ import annotations

from pathlib import Path

import components
import install
import install_health


def core_repos(root) -> list[str]:
    return [repo["name"] for repo in install.parse_repos(root) if repo["name"] not in components.REPOS.values()]


def core_status(root, repo: str) -> str:
    if install_health.failed(root, repo):
        return "failed"
    return "installed" if (Path(root) / "src" / repo).is_dir() else "to install"


def status(root, name: str, on: bool) -> str:
    repo = components.REPOS.get(name)
    if on and repo and install_health.failed(root, repo):
        return "failed"
    if on:
        return "installed" if components.installed(root, name) else "to install"
    return "to leave out" if components.installed(root, name) else "not installed"


def _labels_with(root, selection: dict[str, bool], wanted: str) -> list[str]:
    core = [repo for repo in core_repos(root) if core_status(root, repo) == wanted]
    return core + [label for name, label in components.LABELS.items()
                   if status(root, name, selection[name]) == wanted]


def summary(root, selection: dict[str, bool]) -> tuple[str, str]:
    failed = _labels_with(root, selection, "failed")
    if failed:
        return f"Failed: {', '.join(failed)}", "failed"
    missing = _labels_with(root, selection, "to install")
    if missing:
        return f"Installing: {', '.join(missing)}", "to install"
    return "Everything is installed", "installed"
