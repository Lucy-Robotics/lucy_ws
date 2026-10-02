#!/usr/bin/env python3
"""
Windows-native colcon build wrapper.

Runs colcon build with the Windows workspace configuration under the MSVC
environment (ROS 2 C++ packages need cl.exe, which only exists inside a Visual
Studio developer environment).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from install import msvc_available, msvc_environment  # noqa: E402

COLCON_ARGS = [
    "build",
    "--merge-install",
    "--cmake-args",
    "-GNinja",
    "-DCMAKE_BUILD_TYPE=Release",
    "-Wno-dev",
]


def build_env() -> dict:
    """Environment for colcon: MSVC vars folded in on Windows, unchanged elsewhere."""
    if sys.platform != "win32":
        return dict(os.environ)

    msvc = msvc_environment()
    if msvc is None:
        if msvc_available():
            return dict(os.environ)  # already inside a developer prompt
        print(
            "warning: MSVC toolchain not found; C++ packages will fail to configure.\n"
            "         Install the Visual Studio Build Tools with the 'Desktop "
            "development with C++' workload.",
            file=sys.stderr,
        )
        return dict(os.environ)

    # vcvars wins on PATH/INCLUDE/LIB; keep Pixi's own vars for everything else.
    return {**os.environ, **msvc}


def main() -> int:
    # colcon's console-script shim cannot launch an interpreter whose path contains
    # a space, so go through the interpreter directly.
    command = [sys.executable, "-m", "colcon", *COLCON_ARGS, *sys.argv[1:]]
    return subprocess.call(command, cwd=ROOT, env=build_env())


if __name__ == "__main__":
    raise SystemExit(main())
