#!/usr/bin/env python3

import json
import os
import pathlib


def lucy_ws_branch(caller: str, caller_ref: str, master_side: bool) -> str:
    if caller == "lucy_ws":
        return caller_ref
    return "master" if master_side else "dev"


def pick(config: dict, caller: str, caller_ref: str, master_side: bool, overrides: str = "") -> dict:
    for repo in config["repos"]:
        repo["branch"] = caller_ref if repo["name"] == caller else ("master" if master_side else "dev")
    by_name = {repo["name"]: repo for repo in config["repos"]}
    for entry in overrides.split():
        name, sep, branch = entry.partition("=")
        if not sep or not branch or name not in by_name:
            raise SystemExit(f"bad branch override {entry!r}: use <repo>=<branch> with a repo from {sorted(by_name)}")
        by_name[name]["branch"] = branch
    return config


def main() -> None:
    caller = os.environ["CALLER"]
    caller_ref = os.environ["CALLER_REF"]
    master_side = os.environ["MASTER_SIDE"] == "true"
    path = pathlib.Path("config/repos.json")
    config = pick(json.loads(path.read_text()), caller, caller_ref, master_side, os.environ.get("BRANCHES", ""))
    path.write_text(json.dumps(config, indent=2))
    for repo in config["repos"]:
        print(repo["name"], repo["branch"])
    print("lucy_ws", lucy_ws_branch(caller, caller_ref, master_side))


if __name__ == "__main__":
    main()
