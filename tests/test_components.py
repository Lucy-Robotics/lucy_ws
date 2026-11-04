import components


def _choice(**changes):
    return {**components.DEFAULTS, **changes}


def test_defaults_install_everything_but_simulation_and_marty(tmp_path):
    assert components.load(tmp_path) == _choice(simulation=False, robot_marty=False)
    assert all(on for name, on in components.load(tmp_path).items() if name not in components.OFF_BY_DEFAULT)
    assert components.pixi_env(components.load(tmp_path)) == "default"


def test_save_keeps_other_env_lines_and_round_trips(tmp_path):
    (tmp_path / ".env").write_text("DEV=true\nLUCY_SIMULATION=false\n")
    choice = _choice(simulation=True, visualisation=False, control_panel=False, robot_inmoov=False)
    components.save(tmp_path, choice)
    text = (tmp_path / ".env").read_text()
    assert "DEV=true" in text
    assert text.count("LUCY_SIMULATION=") == 1
    assert "LUCY_PIXI_ENV=minimal-sim" in text
    assert components.load(tmp_path) == choice


def test_each_combination_has_its_own_pixi_environment():
    envs = {components.pixi_env({"simulation": s, "visualisation": v}) for s in (False, True) for v in (False, True)}
    assert envs == {"default", "sim", "minimal", "minimal-sim"}


def test_pixi_command_targets_the_chosen_environment(tmp_path):
    components.save(tmp_path, _choice(simulation=True))
    assert components.pixi_command(tmp_path, ["run", "build"]) == ["pixi", "run", "-e", "sim", "build"]
    assert components.pixi_command(tmp_path, ["install"]) == ["pixi", "install", "-e", "sim"]
    assert components.pixi_command(tmp_path, ["lock"]) == ["pixi", "lock"]


def test_a_choice_without_any_robot_is_refused():
    no_robot = _choice(**{robot: False for robot in components.ROBOTS})
    assert components.problems(no_robot) == ["Pick at least one robot"]
    assert components.problems(_choice(robot_inmoov=False)) == []


def test_left_out_clones_are_ignored_by_colcon_until_picked_again(tmp_path):
    for repo in ("inmoov_urdf", "lucy_embedded_firmware", "so_arm101_urdf"):
        (tmp_path / "src" / repo).mkdir(parents=True)
    choice = _choice(robot_inmoov=False, firmware=False)
    assert sorted(components.mark_left_out(tmp_path, choice)) == ["inmoov_urdf", "lucy_embedded_firmware"]
    assert not (tmp_path / "src" / "so_arm101_urdf" / "COLCON_IGNORE").exists()
    components.mark_left_out(tmp_path, _choice())
    assert not (tmp_path / "src" / "inmoov_urdf" / "COLCON_IGNORE").exists()


def test_picking_a_repo_keeps_a_colcon_ignore_someone_else_wrote(tmp_path):
    repo = tmp_path / "src" / "inmoov_urdf"
    repo.mkdir(parents=True)
    (repo / "COLCON_IGNORE").touch()
    components.mark_left_out(tmp_path, _choice())
    assert (repo / "COLCON_IGNORE").exists()


def test_launcher_hides_packages_of_components_left_out(tmp_path, monkeypatch):
    from launcher import package

    monkeypatch.setattr(package, "WORKSPACE_ROOT", tmp_path)
    components.save(tmp_path, _choice(control_panel=False, firmware=False, robot_inmoov=False))
    for left_out in ("simulation", "control_panel", "firmware", "robot_inmoov"):
        assert not package._pkg_visible({"requires_component": left_out}, dev_mode=False)
    assert package._pkg_visible({"requires_component": "visualisation"}, dev_mode=False)
    assert package._pkg_visible({"requires_component": "robot_so_arm101"}, dev_mode=False)
    assert package._pkg_visible({}, dev_mode=False)
