import components


def test_defaults_are_visualisation_and_panel_without_simulation(tmp_path):
    assert components.load(tmp_path) == {"simulation": False, "visualisation": True, "control_panel": True}
    assert components.pixi_env(components.load(tmp_path)) == "default"


def test_save_keeps_other_env_lines_and_round_trips(tmp_path):
    (tmp_path / ".env").write_text("DEV=true\nLUCY_SIMULATION=false\n")
    choice = {"simulation": True, "visualisation": False, "control_panel": False}
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
    components.save(tmp_path, {"simulation": True, "visualisation": True, "control_panel": True})
    assert components.pixi_command(tmp_path, ["run", "build"]) == ["pixi", "run", "-e", "sim", "build"]
    assert components.pixi_command(tmp_path, ["install"]) == ["pixi", "install", "-e", "sim"]
    assert components.pixi_command(tmp_path, ["lock"]) == ["pixi", "lock"]

