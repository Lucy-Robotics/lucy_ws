from __future__ import annotations

import os
import shutil
from pathlib import Path


def env_vc_runtime(prefix: Path) -> list[Path]:
    bin_dir = prefix / "Library" / "bin"
    return sorted([*bin_dir.glob("vcruntime140*.dll"), *bin_dir.glob("msvcp140*.dll")])


def is_current(target: Path, source: Path) -> bool:
    if not target.exists():
        return False
    placed, wanted = target.stat(), source.stat()
    return (placed.st_size, placed.st_mtime_ns) == (wanted.st_size, wanted.st_mtime_ns)


def place_env_vc_runtime(prefix: Path) -> None:
    runtime = env_vc_runtime(prefix)
    for exe_dir in {exe.parent for exe in (prefix / "Library" / "lib").glob("*/*.exe")}:
        for dll in runtime:
            target = exe_dir / dll.name
            if is_current(target, dll):
                continue
            try:
                target.unlink(missing_ok=True)
            except OSError:
                continue
            try:
                os.link(dll, target)
            except OSError:
                shutil.copy2(dll, target)
