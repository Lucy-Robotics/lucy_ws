#!/usr/bin/env python3

import json
import os
import pathlib


def lucy_ws_branch(caller: str, caller_ref: str, master_side: bool) -> str:
    if caller == "lucy_ws":
        return caller_ref
    return "master" if master_side else "dev"


def pick(config: dict, caller: str, caller_ref: str, master_side: bool) -> dict:
    for repo in config["repos"]:
        repo["branch"] = caller_ref if repo["name"] == caller else ("master" if master_side else "dev")
    return config


def main() -> None:
    caller = os.environ["CALLER"]
    caller_ref = os.environ["CALLER_REF"]
    master_side = os.environ["MASTER_SIDE"] == "true"
    path = pathlib.Path("config/repos.json")
    config = pick(json.loads(path.read_text()), caller, caller_ref, master_side)
    path.write_text(json.dumps(config, indent=2))
    for repo in config["repos"]:
        print(repo["name"], repo["branch"])
    print("lucy_ws", lucy_ws_branch(caller, caller_ref, master_side))


if __name__ == "__main__":
    main()
