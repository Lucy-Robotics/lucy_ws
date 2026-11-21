import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ci_stack import path_outside


def test_path_outside_drops_only_entries_under_the_workspace():
    entries = ["/ws/.pixi/envs/default/bin", "/usr/bin", "/WS/install/lib", "/opt/ws/bin"]
    assert path_outside("/ws", os.pathsep.join(entries)) == os.pathsep.join(["/usr/bin", "/opt/ws/bin"])
