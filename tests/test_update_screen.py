import curses
import json
import subprocess

import pytest

import Lucy
import components
import install_health
import tui_toolbox
import update_branches
import update_screen
import update_status
from update_branches import WORKSPACE

UP, DOWN, RIGHT, LEFT, ENTER, SPACE, ESC = (
    curses.KEY_UP, curses.KEY_DOWN, curses.KEY_RIGHT, curses.KEY_LEFT, ord("\n"), ord(" "), 27)
TO_MARTY = [UP, UP, UP]
TO_CORE_REPO = [UP, UP]
TO_WORKSPACE = [UP]
TO_FIRST_ROBOT = [UP] * 6
TO_SIMULATION = [UP] * 10


class Screen:
    def __init__(self, keys, size=(Lucy.MIN_TERM_HEIGHT, Lucy.MIN_TERM_WIDTH)):
        self.keys, self.size, self.written, self.drawn, self.lines = list(keys), size, {}, "", {}
        self.attrs = {}

    def getmaxyx(self): return self.size
    def erase(self): self.written, self.drawn, self.lines = {}, "", {}
    def refresh(self): pass
    def getch(self): return self.keys.pop(0)

    def addstr(self, y, x, text, *attr):
        self.attrs[text] = attr[0] if attr else 0
        assert y < self.size[0] and x + len(text) < self.size[1]
        self.written[y] = text
        self.drawn += text
        self.lines[y] = self.lines.get(y, "") + text


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "repos.json").write_text(
        '{"repos": [{"name": "lucy_ros_packages", "branch": "dev", "url_https": "https://x/a.git"},'
        ' {"name": "marty_urdf", "branch": "dev", "url_https": "https://x/m.git"}]}')
    monkeypatch.setattr(update_screen.curses, "curs_set", lambda _: None)
    monkeypatch.setattr(update_screen.curses, "color_pair", lambda _: 0)
    monkeypatch.setattr(tui_toolbox, "setup_colors", lambda: None)
    return tmp_path


def test_update_button_saves_the_choice_and_asks_for_the_update(workspace):
    keys = [*TO_MARTY, SPACE, DOWN, DOWN, DOWN, ENTER]
    assert update_screen.update_screen(Screen(keys), workspace) is not None
    assert components.load(workspace)["robot_marty"] is True


def test_exit_button_leaves_without_saving(workspace):
    keys = [*TO_MARTY, SPACE, DOWN, DOWN, DOWN, DOWN, ENTER]
    assert update_screen.update_screen(Screen(keys), workspace) is None
    assert not (workspace / ".env").exists()


def test_escape_leaves_without_saving(workspace):
    assert update_screen.update_screen(Screen([*TO_MARTY, SPACE, ESC]), workspace) is None
    assert not (workspace / ".env").exists()


@pytest.mark.parametrize("key", ["x", "X"])
def test_x_exits_even_from_a_branch_list(workspace, key):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    screen = Screen([*TO_CORE_REPO, RIGHT, DOWN, ord(key), ENTER])
    assert update_screen.update_screen(screen, workspace) is None
    assert screen.keys == [ENTER]


def test_update_stays_refused_without_a_robot(workspace):
    components.save(workspace, {**components.DEFAULTS, **{robot: False for robot in components.ROBOTS}})
    assert update_screen.update_screen(Screen([ENTER, ESC]), workspace) is None


def test_screen_fits_the_minimum_terminal(workspace):
    screen = Screen([ESC])
    update_screen.update_screen(screen, workspace)
    assert screen.written[Lucy.MIN_TERM_HEIGHT - 2] == "[ Exit ]"


def test_ticking_a_left_out_robot_plans_its_install(workspace):
    repo = workspace / "src" / "marty_urdf"
    repo.mkdir(parents=True)
    (workspace / "install" / "marty_urdf").mkdir(parents=True)
    (repo / "COLCON_IGNORE").write_text(components.LEFT_OUT_MARK)
    assert update_status.status(workspace, "robot_marty", False) == "not installed"
    assert update_status.status(workspace, "robot_marty", True) == "to install"
    selection = {**components.load(workspace), "robot_marty": True}
    assert "Robot: Marty" in update_status.summary(workspace, selection)[0]


def test_unticking_an_installed_robot_says_it_will_be_left_out(workspace):
    (workspace / "src" / "marty_urdf").mkdir(parents=True)
    (workspace / "install" / "marty_urdf").mkdir(parents=True)
    assert update_status.status(workspace, "robot_marty", False) == "to leave out"


def test_a_cloned_robot_that_was_never_built_is_still_to_install(workspace):
    (workspace / "src" / "marty_urdf").mkdir(parents=True)
    assert update_status.status(workspace, "robot_marty", True) == "to install"


def test_simulation_counts_as_installed_only_when_its_environment_is_the_saved_one(workspace):
    (workspace / ".pixi" / "envs" / "sim").mkdir(parents=True)
    assert update_status.status(workspace, "simulation", True) == "to install"
    components.save(workspace, {**components.DEFAULTS, "simulation": True})
    assert update_status.status(workspace, "simulation", True) == "installed"


def test_a_package_whose_colcon_build_failed_shows_as_failed(workspace):
    (workspace / "src" / "marty_urdf").mkdir(parents=True)
    (workspace / "src" / "marty_urdf" / "package.xml").touch()
    (workspace / "build" / "marty_urdf").mkdir(parents=True)
    (workspace / "build" / "marty_urdf" / "colcon_build.rc").write_text("1")
    assert update_status.status(workspace, "robot_marty", True) == "failed"
    selection = {**components.load(workspace), "robot_marty": True}
    assert update_status.summary(workspace, selection) == ("Failed: Robot: Marty", "failed")


def test_a_failed_package_of_a_multi_package_repo_fails_the_repo(workspace):
    package = workspace / "src" / "lucy_ros_packages" / "lucy_msgs"
    package.mkdir(parents=True)
    (package / "package.xml").touch()
    (workspace / "build" / "lucy_msgs").mkdir(parents=True)
    (workspace / "build" / "lucy_msgs" / "colcon_build.rc").write_text("SIGINT")
    assert update_status.core_status(workspace, "lucy_ros_packages") == "failed"


def test_a_failed_install_step_stays_failed_until_it_succeeds(workspace):
    with pytest.raises(RuntimeError):
        with install_health.tracked(workspace, "marty_urdf"):
            raise RuntimeError("no fast-forward")
    assert install_health.failed(workspace, "marty_urdf")
    with install_health.tracked(workspace, "marty_urdf"):
        pass
    assert not install_health.failed(workspace, "marty_urdf")


def _repo_with_branches(path, *names):
    subprocess.run(["git", "init", "-q", "-b", "dev", str(path)], check=True)
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    for name in names:
        subprocess.run([*git, "branch", name], check=True)


def test_right_enters_the_branches_and_down_picks_the_next_one(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature", "zeta")
    keys = [*TO_CORE_REPO, RIGHT, DOWN, LEFT, DOWN, DOWN, ENTER]
    assert update_screen.update_screen(Screen(keys), workspace) is not None
    pins = json.loads((workspace / "config" / "repos.json.local").read_text())
    assert pins["repos"][0]["branch"] == "feature"


def test_up_and_down_move_between_rows_until_right_is_pressed(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    assert update_screen.update_screen(Screen([*TO_CORE_REPO, DOWN, DOWN, DOWN, ENTER]), workspace) is None
    assert not (workspace / "config" / "repos.json.local").exists()


def test_escape_inside_the_branches_only_leaves_the_branches(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    screen = Screen([*TO_CORE_REPO, RIGHT, ESC, ESC])
    assert update_screen.update_screen(screen, workspace) is None
    assert not screen.keys


def test_a_picked_branch_is_in_the_file_without_pressing_update(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    assert update_screen.update_screen(Screen([*TO_CORE_REPO, RIGHT, DOWN, LEFT, ESC]), workspace) is None
    pins = json.loads((workspace / "config" / "repos.json.local").read_text())
    assert pins["repos"][0]["branch"] == "feature"


def test_picking_a_branch_then_going_back_restores_the_file(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    assert update_screen.update_screen(Screen([*TO_CORE_REPO, RIGHT, DOWN, UP, LEFT, ESC]), workspace) is None
    pins = json.loads((workspace / "config" / "repos.json.local").read_text())
    assert pins["repos"][0]["branch"] == "dev"


def test_opening_the_screen_shows_a_branch_edited_in_the_file(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    data = json.loads((workspace / "config" / "repos.json").read_text())
    data["repos"][0]["branch"] = "feature"
    (workspace / "config" / "repos.json.local").write_text(json.dumps(data))
    assert update_screen.BranchPicker(workspace).targets["lucy_ros_packages"] == "feature"


def _rows(workspace):
    rows = json.loads((workspace / "config" / "repos.json.local").read_text())["repos"]
    return {row["name"]: row for row in rows}


def test_a_toggled_component_is_in_the_file_without_pressing_update(workspace):
    assert update_screen.update_screen(Screen([*TO_MARTY, SPACE, ESC]), workspace) is None
    assert _rows(workspace)["marty_urdf"]["enabled"] is True
    assert components.load(workspace)["robot_marty"] is True


def test_toggling_a_component_twice_turns_it_back_off_in_the_file(workspace):
    assert update_screen.update_screen(Screen([*TO_MARTY, SPACE, SPACE, ESC]), workspace) is None
    assert _rows(workspace)["marty_urdf"]["enabled"] is False


def test_turning_off_every_robot_leaves_the_file_alone(workspace):
    data = json.loads((workspace / "config" / "repos.json").read_text())
    data["repos"].append({"name": "inmoov_urdf", "branch": "dev", "url_https": "https://x/i.git"})
    (workspace / "config" / "repos.json").write_text(json.dumps(data))
    components.save(workspace, {**components.DEFAULTS, **{robot: False for robot in components.ROBOTS[1:]}})
    before = (workspace / "config" / "repos.json.local").read_text()
    screen = Screen([*TO_FIRST_ROBOT, SPACE, ESC])
    assert update_screen.update_screen(screen, workspace) is None
    assert "Pick at least one robot" in screen.drawn
    assert (workspace / "config" / "repos.json.local").read_text() == before


def test_toggling_simulation_waits_for_update_because_it_picks_the_pixi_environment(workspace):
    screen = Screen([*TO_SIMULATION, SPACE, ESC])
    assert update_screen.update_screen(screen, workspace) is None
    assert not (workspace / ".env").exists()
    assert not (workspace / "config" / "repos.json.local").exists()


def test_update_without_a_branch_change_writes_no_pin_file(workspace):
    assert update_screen.update_screen(Screen([ENTER]), workspace) is not None
    assert not (workspace / "config" / "repos.json.local").exists()


def test_the_focused_repo_lists_its_branches_on_separate_lines(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    screen = Screen([*TO_CORE_REPO, ESC])
    update_screen.update_screen(screen, workspace)
    assert "dev" in screen.lines[10] and "feature" in screen.lines[11]


def test_other_rows_only_show_their_own_branch(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    screen = Screen([ESC])
    update_screen.update_screen(screen, workspace)
    assert "feature" not in screen.drawn


def test_a_picked_branch_turns_the_checkbox_yellow(workspace, monkeypatch):
    monkeypatch.setattr(update_screen.curses, "color_pair", lambda pair: pair)
    assert update_screen.check_attr("installed", True) == tui_toolbox.YELLOW
    assert update_screen.check_attr("installed", False) == tui_toolbox.GREEN


def test_the_branch_the_repo_is_on_keeps_its_own_color_while_picking(workspace, monkeypatch):
    monkeypatch.setattr(update_screen.curses, "color_pair", lambda pair: pair)
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature", "zeta")
    screen = Screen([*TO_CORE_REPO, RIGHT, DOWN, ord("x")])
    update_screen.update_screen(screen, workspace)
    assert screen.attrs["dev"] == tui_toolbox.CYAN
    assert screen.attrs["feature"] == curses.A_REVERSE
    assert screen.attrs["zeta"] == curses.A_DIM


def test_a_picked_branch_is_listed_as_a_pending_switch(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    screen = Screen([*TO_CORE_REPO, RIGHT, DOWN, LEFT, ESC])
    update_screen.update_screen(screen, workspace)
    assert "Switching: lucy_ros_packages -> feature" in screen.drawn


def test_the_workspace_branch_is_handed_back_and_never_pinned(workspace):
    _repo_with_branches(workspace, "feature")
    keys = [*TO_WORKSPACE, RIGHT, DOWN, LEFT, DOWN, ENTER]
    assert update_screen.update_screen(Screen(keys), workspace) == "feature"
    assert not (workspace / "config" / "repos.json.local").exists()


def test_a_workspace_switch_restarts_lucy_on_the_new_code(monkeypatch):
    calls = []
    monkeypatch.setattr(Lucy.os, "execv", lambda path, args: calls.append(args))
    Lucy.restart_if_switched({"restart": True})
    Lucy.restart_if_switched({})
    assert len(calls) == 1 and calls[0][-1] == "Lucy.py"


def test_switching_the_workspace_checks_out_before_installing_and_restarts(monkeypatch):
    monkeypatch.setattr(Lucy, "current_branch", lambda _: "dev")
    task = Lucy.update_task("feature")
    assert task["cmd"] == ["git", "checkout", "feature"]
    assert task["followup"][0][-1] == "install.py"
    assert task["restart"]


@pytest.mark.parametrize("branch", ["dev", ""])
def test_staying_on_the_workspace_branch_only_installs(monkeypatch, branch):
    monkeypatch.setattr(Lucy, "current_branch", lambda _: "dev")
    task = Lucy.update_task(branch)
    assert task["cmd"][-1] == "install.py" and "restart" not in task


def test_the_focused_repo_shows_its_version_and_last_update_at_the_bottom(workspace):
    repo = workspace / "src" / "lucy_ros_packages"
    _repo_with_branches(repo)
    (repo / "version.txt").write_text("v1.2.3\n")
    (repo / ".git" / "FETCH_HEAD").touch()
    screen = Screen([*TO_CORE_REPO, ESC])
    update_screen.update_screen(screen, workspace)
    assert screen.written[Lucy.MIN_TERM_HEIGHT - 1].startswith("Version v1.2.3-g")
    assert "Last updated 20" in screen.written[Lucy.MIN_TERM_HEIGHT - 1]


def test_a_tagged_repo_uses_git_describe_as_its_version(tmp_path):
    _repo_with_branches(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "tag", "v9.9.9"], check=True)
    (tmp_path / "version.txt").write_text("v0.0.1\n")
    assert update_branches.version(tmp_path) == "v9.9.9"


def test_a_zip_install_falls_back_to_the_declared_version(tmp_path):
    (tmp_path / "version.txt").write_text("v0.0.1\n")
    assert update_branches.version(tmp_path) == "v0.0.1"


def test_a_repo_that_was_never_fetched_says_so(tmp_path):
    assert update_branches.last_update(tmp_path) == "never"
    assert update_branches.details(tmp_path / "missing") == "Not cloned yet"


@pytest.mark.parametrize("current, target, text", [
    ("", "dev", "-> dev"),
    ("dev", "dev", "dev"),
    ("wip", "dev", "wip -> dev"),
])
def test_branch_text_shows_where_update_takes_the_repo(current, target, text):
    assert update_branches.branch_text(current, target) == text
