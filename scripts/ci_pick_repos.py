#!/usr/bin/env python3

import json
import os
import pathlib
import subprocess
from typing import Callable

LUCY_WS_URL = "https://github.com/Lucy-Robotics/lucy_ws.git"

HasBranch = Callable[[str, str], bool]


def no_branch(url: str, branch: str) -> bool:
    return False


def remote_has_branch(url: str, branch: str) -> bool:
    found = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", url, branch], capture_output=True)
    return found.returncode == 0


def _base_branch(url: str, caller_ref: str, master_side: bool, has_branch: HasBranch) -> str:
    if master_side:
        return "master"
    return caller_ref if has_branch(url, caller_ref) else "dev"


def lucy_ws_branch(
    caller: str, caller_ref: str, master_side: bool, overrides: str = "", has_branch: HasBranch = no_branch
) -> str:
    pinned = dict(entry.partition("=")[::2] for entry in overrides.split())
    default = caller_ref if caller == "lucy_ws" else _base_branch(LUCY_WS_URL, caller_ref, master_side, has_branch)
    return pinned.get("lucy_ws", default)


def pick(
    config: dict,
    caller: str,
    caller_ref: str,
    master_side: bool,
    overrides: str = "",
    has_branch: HasBranch = no_branch,
) -> dict:
    for repo in config["repos"]:
        repo["branch"] = (
            caller_ref
            if repo["name"] == caller
            else _base_branch(repo.get("url_https", ""), caller_ref, master_side, has_branch)
        )
    by_name = {repo["name"]: repo for repo in config["repos"]}
    names = sorted([*by_name, "lucy_ws"])
    for entry in overrides.split():
        name, sep, branch = entry.partition("=")
        if not sep or not branch or name not in names:
            raise SystemExit(f"bad branch override {entry!r}: use <repo>=<branch> with a repo from {names}")
        if name in by_name:
            by_name[name]["branch"] = branch
    return config


def main() -> None:
    caller = os.environ["CALLER"]
    caller_ref = os.environ["CALLER_REF"]
    master_side = os.environ["MASTER_SIDE"] == "true"
    path = pathlib.Path("config/repos.json")
    overrides = os.environ.get("BRANCHES", "")
    config = pick(json.loads(path.read_text()), caller, caller_ref, master_side, overrides, remote_has_branch)
    path.write_text(json.dumps(config, indent=2))
    for repo in config["repos"]:
        print(repo["name"], repo["branch"])
    print("lucy_ws", lucy_ws_branch(caller, caller_ref, master_side, overrides, remote_has_branch))


if __name__ == "__main__":
    main()
