"""Tests for the optional-repo colcon skip (COLCON_IGNORE) in install.py."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402


def _workspace(tmp_path: Path, repos: list[dict], with_src: bool = True) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "repos.json").write_text(json.dumps({"repos": repos}), encoding="utf-8")
    if with_src:
        for repo in repos:
            (tmp_path / "src" / repo["name"]).mkdir(parents=True, exist_ok=True)
    return tmp_path


REQUIRED = {
    "name": "required_pkg",
    "branch": "main",
    "url_https": "https://example.com/required.git",
}
OPTIONAL = {
    "name": "opt_pkg",
    "branch": "main",
    "optional": True,
    "url_https": "https://example.com/opt.git",
}


def test_mark_optional_colcon_ignore_skips_optional_repos(tmp_path, monkeypatch):
    monkeypatch.delenv("LUCY_BUILD_OPTIONAL", raising=False)
    ws = _workspace(tmp_path, [REQUIRED, OPTIONAL])

    ignored = install.mark_optional_colcon_ignore(ws)

    assert ignored == ["opt_pkg"]
    assert (ws / "src" / "opt_pkg" / "COLCON_IGNORE").is_file()
    assert not (ws / "src" / "required_pkg" / "COLCON_IGNORE").exists()


def test_mark_optional_colcon_ignore_respects_build_optional_flag(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LUCY_BUILD_OPTIONAL", "1")
    ws = _workspace(tmp_path, [OPTIONAL])

    assert install.mark_optional_colcon_ignore(ws) == []
    assert not (ws / "src" / "opt_pkg" / "COLCON_IGNORE").exists()


def test_mark_optional_colcon_ignore_skips_repos_not_cloned(tmp_path, monkeypatch):
    monkeypatch.delenv("LUCY_BUILD_OPTIONAL", raising=False)
    ws = _workspace(tmp_path, [OPTIONAL], with_src=False)

    assert install.mark_optional_colcon_ignore(ws) == []


def test_parse_repos_keeps_optional_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("DEV", raising=False)
    ws = _workspace(tmp_path, [REQUIRED, OPTIONAL], with_src=False)

    rows = {r["name"]: r for r in install.parse_repos(ws)}

    assert rows["opt_pkg"]["optional"] is True
    assert rows["required_pkg"]["optional"] is False
