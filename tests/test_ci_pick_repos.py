import importlib.util
from pathlib import Path

import pytest

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


def test_overrides_pin_the_named_repos_and_leave_the_rest_on_dev():
    picked = _module().pick(_config(), "lucy_ws", "dev", master_side=False, overrides="lucy_control_panel=aes/#12/x")
    assert {r["name"]: r["branch"] for r in picked["repos"]} == {"lucy_ros_packages": "dev", "lucy_control_panel": "aes/#12/x"}


def test_unknown_or_malformed_override_stops_the_run():
    for overrides in ("lucy_panel=aes/x", "lucy_control_panel", "lucy_control_panel="):
        with pytest.raises(SystemExit):
            _module().pick(_config(), "lucy_ws", "dev", master_side=False, overrides=overrides)


def test_lucy_ws_override_pins_the_workspace_and_leaves_sub_repos_on_dev():
    m = _module()
    picked = m.pick(_config(), "lucy_ws", "dev", master_side=False, overrides="lucy_ws=aes/fix-tui")
    assert {r["branch"] for r in picked["repos"]} == {"dev"}
    assert m.lucy_ws_branch("lucy_ws", "dev", False, "lucy_ws=aes/fix-tui") == "aes/fix-tui"


def _has(*pairs):
    return lambda url, branch: (url, branch) in pairs


def test_sub_repos_with_a_branch_of_the_same_name_build_it():
    config = {
        "repos": [
            {"name": "inmoov_i2_urdf", "url_https": "i2.git"},
            {"name": "lucy_control_panel", "url_https": "lcp.git"},
        ]
    }
    picked = _module().pick(config, "lucy_ws", "aes/latest", False, has_branch=_has(("i2.git", "aes/latest")))
    assert {r["name"]: r["branch"] for r in picked["repos"]} == {
        "inmoov_i2_urdf": "aes/latest",
        "lucy_control_panel": "dev",
    }


def test_master_side_ignores_branches_of_the_same_name():
    config = {"repos": [{"name": "inmoov_i2_urdf", "url_https": "i2.git"}]}
    picked = _module().pick(config, "lucy_ws", "master", True, has_branch=lambda url, branch: True)
    assert picked["repos"][0]["branch"] == "master"


def test_lucy_ws_follows_a_sub_repo_branch_it_also_has():
    m = _module()
    has = _has((m.LUCY_WS_URL, "aes/latest"))
    assert m.lucy_ws_branch("lucy_control_panel", "aes/latest", False, has_branch=has) == "aes/latest"
    assert m.lucy_ws_branch("lucy_control_panel", "aes/other", False, has_branch=has) == "dev"


def test_overrides_win_over_branches_of_the_same_name():
    config = {"repos": [{"name": "inmoov_i2_urdf", "url_https": "i2.git"}]}
    picked = _module().pick(
        config, "lucy_ws", "aes/latest", False, "inmoov_i2_urdf=aes/fix", has_branch=lambda url, branch: True
    )
    assert picked["repos"][0]["branch"] == "aes/fix"
