from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import install

WORKSPACE = "lucy_ws"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False).stdout.strip()


def current_branch(repo: Path) -> str:
    if not (repo / ".git").exists():
        return ""
    return _git(repo, "branch", "--show-current") or _git(repo, "rev-parse", "--short", "HEAD")


def declared_version(repo: Path) -> str:
    file = repo / "version.txt"
    return file.read_text().strip() if file.is_file() else ""


def version(repo: Path) -> str:
    declared = declared_version(repo)
    if not (repo / ".git").exists():
        return declared
    described = _git(repo, "describe", "--tags", "--always")
    if not declared or described.startswith("v"):
        return described
    return f"{declared}-g{described}"


def last_update(repo: Path) -> str:
    fetched = repo / ".git" / "FETCH_HEAD"
    if not fetched.is_file():
        return "never"
    return datetime.fromtimestamp(fetched.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def details(repo: Path) -> str:
    if not repo.is_dir():
        return "Not cloned yet"
    return f"Version {version(repo)}  Last updated {last_update(repo)}"


def available_branches(repo: Path) -> list[str]:
    if not (repo / ".git").exists():
        return []
    refs = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").splitlines()
    return sorted({ref.removeprefix("origin/") for ref in refs if ref not in ("origin", "origin/HEAD")})


def branch_text(current: str, target: str) -> str:
    if not current:
        return f"-> {target}"
    return current if current == target else f"{current} -> {target}"


class BranchPicker:
    def __init__(self, root) -> None:
        self.root = Path(root)
        src = self.root / "src"
        self.pins = {repo["name"]: repo["branch"] for repo in install.parse_repos(root)}
        paths = {name: src / name for name in self.pins}
        self.targets = dict(self.pins)
        workspace_branch = current_branch(self.root)
        if workspace_branch:
            self.targets[WORKSPACE] = workspace_branch
            paths[WORKSPACE] = self.root
        self.current = {name: current_branch(path) for name, path in paths.items()}
        self.details = {name: details(path) for name, path in paths.items()}
        self.options = {name: sorted({self.targets[name], *available_branches(path)})
                        for name, path in paths.items()}

    def shift(self, repo: str, delta: int) -> None:
        options = self.options[repo]
        self.targets[repo] = options[(options.index(self.targets[repo]) + delta) % len(options)]

    def pending(self, repo: str) -> bool:
        return bool(self.current[repo]) and self.targets[repo] != self.current[repo]

    def changes(self, left_out: set[str]) -> list[str]:
        return [f"{repo} -> {target}" for repo, target in self.targets.items()
                if repo not in left_out and self.pending(repo)]

    def text(self, repo: str) -> str:
        return branch_text(self.current[repo], self.targets[repo])

    def save(self) -> None:
        if all(self.targets[name] == pin for name, pin in self.pins.items()):
            return
        data = json.loads(install.repos_config_path(self.root).read_text())
        for repo in data["repos"]:
            if repo.get("name") in self.pins:
                repo["branch"] = self.targets[repo["name"]]
        (self.root / "config" / "repos.json.local").write_text(json.dumps(data, indent=2) + "\n")
