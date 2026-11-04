from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


def _marker(root, repo: str) -> Path:
    return Path(root) / "log" / "install_failures" / repo


@contextmanager
def tracked(root, repo: str):
    marker = _marker(root, repo)
    try:
        yield
    except Exception as exc:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{exc}\n")
        raise
    marker.unlink(missing_ok=True)


def _packages(root, repo: str) -> list[str]:
    repo_dir = Path(root) / "src" / repo
    found = [*repo_dir.glob("package.xml"), *repo_dir.glob("*/package.xml")]
    return [path.parent.name for path in found if not (path.parent / "COLCON_IGNORE").exists()]


def _build_failed(root, package: str) -> bool:
    result = Path(root) / "build" / package / "colcon_build.rc"
    return result.is_file() and result.read_text().strip() != "0"


def failed(root, repo: str) -> bool:
    return _marker(root, repo).is_file() or any(_build_failed(root, name) for name in _packages(root, repo))
