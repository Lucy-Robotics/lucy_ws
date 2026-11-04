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

UP, DOWN, RIGHT, ENTER, SPACE, ESC = curses.KEY_UP, curses.KEY_DOWN, curses.KEY_RIGHT, ord("\n"), ord(" "), 27


class Screen:
    def __init__(self, keys, size=(Lucy.MIN_TERM_HEIGHT, Lucy.MIN_TERM_WIDTH)):
        self.keys, self.size, self.written, self.drawn = list(keys), size, {}, ""

    def getmaxyx(self): return self.size
    def erase(self): self.written, self.drawn = {}, ""
    def refresh(self): pass
    def getch(self): return self.keys.pop(0)

    def addstr(self, y, x, text, *_):
        assert y < self.size[0] and x + len(text) < self.size[1]
        self.written[y] = text
        self.drawn += text


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
    assert update_screen.update_screen(Screen([UP, UP, SPACE, DOWN, DOWN, ENTER]), workspace) is True
    assert components.load(workspace)["robot_marty"] is True


def test_exit_button_leaves_without_saving(workspace):
    assert update_screen.update_screen(Screen([UP, UP, SPACE, DOWN, DOWN, DOWN, ENTER]), workspace) is False
    assert not (workspace / ".env").exists()


def test_escape_leaves_without_saving(workspace):
    assert update_screen.update_screen(Screen([UP, UP, SPACE, ESC]), workspace) is False
    assert not (workspace / ".env").exists()


def test_update_stays_refused_without_a_robot(workspace):
    components.save(workspace, {**components.DEFAULTS, **{robot: False for robot in components.ROBOTS}})
    assert update_screen.update_screen(Screen([ENTER, ESC]), workspace) is False


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


def test_right_arrow_picks_the_next_branch_and_update_pins_it(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature", "zeta")
    assert update_screen.update_screen(Screen([UP, RIGHT, DOWN, ENTER]), workspace) is True
    pins = json.loads((workspace / "config" / "repos.json.local").read_text())
    assert pins["repos"][0]["branch"] == "feature"


def test_exit_forgets_a_picked_branch(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    assert update_screen.update_screen(Screen([UP, RIGHT, ESC]), workspace) is False
    assert not (workspace / "config" / "repos.json.local").exists()


def test_update_without_a_branch_change_writes_no_pin_file(workspace):
    assert update_screen.update_screen(Screen([ENTER]), workspace) is True
    assert not (workspace / "config" / "repos.json.local").exists()


def test_the_focused_repo_lists_its_branches_and_the_others_only_their_own(workspace):
    _repo_with_branches(workspace / "src" / "lucy_ros_packages", "feature")
    wide = (Lucy.MIN_TERM_HEIGHT, 120)
    unfocused = Screen([ESC], wide)
    update_screen.update_screen(unfocused, workspace)
    assert "feature" not in unfocused.drawn
    focused = Screen([UP, ESC], wide)
    update_screen.update_screen(focused, workspace)
    assert "feature" in focused.drawn


def test_the_focused_repo_shows_its_version_and_last_update_at_the_bottom(workspace):
    repo = workspace / "src" / "lucy_ros_packages"
    _repo_with_branches(repo)
    (repo / "version.txt").write_text("v1.2.3\n")
    (repo / ".git" / "FETCH_HEAD").touch()
    screen = Screen([UP, ESC])
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
