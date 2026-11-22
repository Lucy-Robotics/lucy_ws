from pathlib import Path

from conftest import TEST_STATE_HOME


def test_the_launcher_keeps_test_state_out_of_the_users_state_directory():
    from launcher import constants

    assert Path(constants.STATE_ROOT).is_relative_to(TEST_STATE_HOME)
    assert not Path(constants.STATE_ROOT).is_relative_to(
        Path.home() / ".local" / "state"
    )
