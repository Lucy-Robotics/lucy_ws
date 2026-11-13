#!/usr/bin/env python3

import json
import os
import pathlib


def lucy_ws_branch(caller: str, caller_ref: str, master_side: bool, overrides: str = "") -> str:
    pinned = dict(entry.partition("=")[::2] for entry in overrides.split())
    default = caller_ref if caller == "lucy_ws" else ("master" if master_side else "dev")
    return pinned.get("lucy_ws", default)


def pick(config: dict, caller: str, caller_ref: str, master_side: bool, overrides: str = "") -> dict:
    for repo in config["repos"]:
        repo["branch"] = caller_ref if repo["name"] == caller else ("master" if master_side else "dev")
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
    config = pick(json.loads(path.read_text()), caller, caller_ref, master_side, overrides)
    path.write_text(json.dumps(config, indent=2))
    for repo in config["repos"]:
        print(repo["name"], repo["branch"])
    print("lucy_ws", lucy_ws_branch(caller, caller_ref, master_side, overrides))


if __name__ == "__main__":
    main()
