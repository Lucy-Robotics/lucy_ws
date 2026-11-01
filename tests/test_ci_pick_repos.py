import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("ci_pick_repos", ROOT / "scripts" / "ci_pick_repos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config():
    return {"repos": [{"name": "lucy_ros_packages", "branch": "master"}, {"name": "lucy_control_panel", "branch": "master"}]}


def test_sub_repos_follow_dev_and_the_caller_its_own_ref():
    picked = _module().pick(_config(), "lucy_control_panel", "aes/fix", master_side=False)
    assert {r["name"]: r["branch"] for r in picked["repos"]} == {"lucy_ros_packages": "dev", "lucy_control_panel": "aes/fix"}


def test_master_side_follows_master():
    picked = _module().pick(_config(), "lucy_ws", "master", master_side=True)
    assert {r["branch"] for r in picked["repos"]} == {"master"}


def test_lucy_ws_branch_is_the_ref_under_test():
    m = _module()
    assert m.lucy_ws_branch("lucy_ws", "aes/ci", master_side=False) == "aes/ci"
    assert m.lucy_ws_branch("lucy_control_panel", "aes/fix", master_side=False) == "dev"
    assert m.lucy_ws_branch("lucy_control_panel", "master", master_side=True) == "master"
