import json

import pytest

import components
import install
import repos_file


def _write(path, rows):
    path.write_text(json.dumps({"repos": rows}))


def _row(name, **fields):
    return {"name": name, "branch": "dev", "url_https": f"https://x/{name}.git", **fields}


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "config").mkdir()
    _write(tmp_path / "config" / "repos.json", [_row("lucy_ros_packages"), _row("marty_urdf")])
    return tmp_path


def _local(workspace):
    return workspace / "config" / "repos.json.local"


def test_enabled_in_the_file_beats_the_env_file(workspace):
    (workspace / ".env").write_text("LUCY_ROBOT_MARTY=false\n")
    _write(_local(workspace), [_row("marty_urdf", enabled=True)])
    assert components.load(workspace)["robot_marty"] is True


def test_a_repo_without_enabled_keeps_the_env_choice(workspace):
    (workspace / ".env").write_text("LUCY_ROBOT_MARTY=true\n")
    _write(_local(workspace), [_row("marty_urdf")])
    assert components.load(workspace)["robot_marty"] is True


@pytest.mark.parametrize("value", ["false", 0, None])
def test_an_enabled_that_is_not_a_boolean_is_ignored(workspace, value):
    (workspace / ".env").write_text("LUCY_ROBOT_MARTY=true\n")
    _write(_local(workspace), [_row("marty_urdf", enabled=value)])
    assert components.load(workspace)["robot_marty"] is True


@pytest.mark.parametrize("text", ["{not json", "[]"])
def test_a_broken_file_falls_back_to_the_env_file(workspace, text):
    (workspace / ".env").write_text("LUCY_ROBOT_MARTY=true\n")
    _local(workspace).write_text(text)
    assert components.load(workspace)["robot_marty"] is True


def test_a_row_without_a_name_cannot_switch_a_component_without_a_repo(workspace):
    _write(_local(workspace), [{"enabled": True}])
    assert components.load(workspace)["simulation"] is False


def test_saving_the_same_choice_creates_no_file_that_would_hide_repos_json(workspace):
    components.save(workspace, components.load(workspace))
    assert not _local(workspace).exists()


def test_saving_a_new_choice_writes_every_known_component_to_the_file(workspace):
    components.save(workspace, {**components.load(workspace), "robot_marty": True})
    rows = {row["name"]: row for row in json.loads(_local(workspace).read_text())["repos"]}
    assert rows["marty_urdf"]["enabled"] is True
    assert "enabled" not in rows["lucy_ros_packages"]


def test_saving_keeps_the_branch_and_extra_fields_of_a_row(workspace):
    _write(_local(workspace), [_row("marty_urdf", branch="mine", optional=True)])
    components.save_repos(workspace, {**components.load(workspace), "robot_marty": True})
    row = json.loads(_local(workspace).read_text())["repos"][0]
    assert (row["branch"], row["optional"], row["enabled"]) == ("mine", True, True)


def test_a_component_missing_from_the_file_is_copied_from_repos_json(workspace):
    _write(_local(workspace), [_row("lucy_ros_packages", branch="mine")])
    components.save_repos(workspace, {**components.load(workspace), "robot_marty": True})
    assert components.load(workspace)["robot_marty"] is True
    assert [row["name"] for row in install.parse_repos(workspace)] == ["lucy_ros_packages", "marty_urdf"]


def test_a_left_out_repo_stays_in_the_file_but_is_not_fetched(workspace):
    components.save(workspace, {**components.load(workspace), "robot_marty": True})
    components.save(workspace, {**components.load(workspace), "robot_marty": False})
    assert "marty_urdf" in {row["name"] for row in install.parse_repos(workspace)}
    assert "marty_urdf" in components.left_out_repos(components.load(workspace))


def test_a_write_leaves_no_temporary_file(workspace):
    repos_file.write(workspace, {"repos": []})
    assert [path.name for path in (workspace / "config").iterdir() if path.suffix == ".tmp"] == []


def test_saving_without_any_repos_file_only_writes_the_env_file(tmp_path):
    (tmp_path / "config").mkdir()
    components.save(tmp_path, {**components.DEFAULTS, "robot_marty": True})
    assert components.load(tmp_path)["robot_marty"] is True
    assert not _local(tmp_path).exists()
