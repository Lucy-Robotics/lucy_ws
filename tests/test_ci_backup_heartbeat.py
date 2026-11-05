import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ci_stack import Ros


def beats(backup_heartbeat, active_client):
    sent = []
    ros = Ros.__new__(Ros)
    ros.backup_heartbeat = backup_heartbeat
    ros.active_client = active_client
    ros.string = lambda data: data
    ros.heartbeat = SimpleNamespace(publish=sent.append)
    ros._beat()
    return sent


def test_beats_for_the_active_client_when_enabled():
    assert beats(True, "cp_1") == ["cp_1"]


def test_stays_silent_when_disabled_or_no_client_is_active():
    assert beats(False, "cp_1") == []
    assert beats(True, "") == []
    assert beats(True, None) == []
