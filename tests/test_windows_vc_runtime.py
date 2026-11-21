import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from windows_vc_runtime import place_env_vc_runtime


def pixi_env(tmp_path):
    bin_dir = tmp_path / "Library" / "bin"
    bin_dir.mkdir(parents=True)
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "rcl.dll"):
        (bin_dir / name).write_bytes(b"14.51")
    rsp = tmp_path / "Library" / "lib" / "robot_state_publisher"
    rsp.mkdir(parents=True)
    (rsp / "robot_state_publisher.exe").write_bytes(b"exe")
    (tmp_path / "Library" / "lib" / "rclpy").mkdir()
    return tmp_path, rsp


def test_cpp_nodes_get_the_env_cpp_runtime_next_to_them(tmp_path):
    prefix, rsp = pixi_env(tmp_path)
    place_env_vc_runtime(prefix)
    assert sorted(p.name for p in rsp.glob("*.dll")) == [
        "msvcp140.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ]
    assert not list((prefix / "Library" / "lib" / "rclpy").iterdir())


def test_an_updated_env_runtime_replaces_the_one_placed_before(tmp_path):
    prefix, rsp = pixi_env(tmp_path)
    place_env_vc_runtime(prefix)
    updated = prefix / "Library" / "bin" / "vcruntime140.dll"
    updated.unlink()
    updated.write_bytes(b"14.52 rebuilt")
    place_env_vc_runtime(prefix)
    assert (rsp / "vcruntime140.dll").read_bytes() == b"14.52 rebuilt"
