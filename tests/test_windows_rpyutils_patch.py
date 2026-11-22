"""Tests for the Windows rpyutils DLL directory lock install.py applies."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

UPSTREAM = '''from contextlib import contextmanager
import os
import sys


@contextmanager
def add_dll_directories_from_env(env_name: str):
    """Add a list of directories from an environment variable to the DLL search path."""
    dll_dir_handles = []
    try:
        yield dll_dir_handles
    finally:
        for handle in dll_dir_handles:
            handle.close()
'''


def _rpyutils(tmp_path: Path) -> Path:
    module = tmp_path / ".pixi" / "envs" / "default" / "Lib" / "site-packages" / "rpyutils" / "add_dll_directories.py"
    module.parent.mkdir(parents=True)
    module.write_text(UPSTREAM, encoding="utf-8")
    return module


def test_patch_locks_once_and_keeps_the_context_manager_working(tmp_path, monkeypatch):
    monkeypatch.setattr(install.sys, "platform", "win32")
    module = _rpyutils(tmp_path)

    assert install.patch_windows_rpyutils_dll_lock(tmp_path, log=lambda _: None) == [str(module)]
    patched = module.read_text(encoding="utf-8")
    assert install.patch_windows_rpyutils_dll_lock(tmp_path, log=lambda _: None) == []
    assert module.read_text(encoding="utf-8") == patched

    spec = importlib.util.spec_from_file_location("patched_rpyutils", module)
    rpyutils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rpyutils)
    with rpyutils.add_dll_directories_from_env("PATH") as outer:
        with rpyutils.add_dll_directories_from_env("PATH") as inner:
            assert outer == inner == []
    assert rpyutils._dll_directories_lock.acquire(blocking=False)


def test_patch_is_a_no_op_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(install.sys, "platform", "linux")
    module = _rpyutils(tmp_path)

    assert install.patch_windows_rpyutils_dll_lock(tmp_path, log=lambda _: None) == []
    assert module.read_text(encoding="utf-8") == UPSTREAM
