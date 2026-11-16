"""The cargo runner keeps colcon's firmware log short: progress is dropped, problems stay."""

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "src" / "lucy_embedded_firmware" / "cmake" / "lucy_cargo_run.cmake"

pytestmark = pytest.mark.skipif(
    shutil.which("cmake") is None or not RUNNER.exists(),
    reason="needs cmake and the firmware repo's cargo runner",
)


def run_runner(tmp_path: Path, script: str, args: tuple = ()):
    fake_cargo = tmp_path / "cargo"
    fake_cargo.write_text("#!/bin/sh\n" + script)
    fake_cargo.chmod(fake_cargo.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        [
            "cmake",
            "-DLABEL=pkg",
            f"-DRUN_COMMAND={fake_cargo}" + "".join(f"|{a}" for a in args),
            "-P",
            str(RUNNER),
        ],
        capture_output=True,
        text=True,
    )


def test_clean_build_prints_one_built_line(tmp_path):
    result = run_runner(
        tmp_path, "echo '   Compiling a v1' >&2\necho '    Finished release' >&2\n"
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "pkg: built"
    assert result.stderr == ""


def test_warning_survives_without_progress_lines(tmp_path):
    result = run_runner(
        tmp_path,
        "echo '   Compiling a v1' >&2\n"
        "echo 'warning: unused dependency `x`; see [docs]' >&2\n",
    )

    assert result.stdout.splitlines() == [
        "warning: unused dependency `x`; see [docs]",
        "pkg: built",
    ]


def test_failed_build_prints_full_log_and_fails(tmp_path):
    result = run_runner(
        tmp_path, "echo '   Compiling a' >&2\necho 'error: boom' >&2\nexit 101\n"
    )

    assert result.returncode != 0
    assert "Compiling a" in result.stdout
    assert "error: boom" in result.stdout
    assert "pkg: build failed (101)" in result.stderr


def test_every_pipe_separated_argument_reaches_the_command(tmp_path):
    result = run_runner(
        tmp_path, 'echo "warning: got $# args: $1 $2" >&2\n', ("build", "--release")
    )

    assert "warning: got 2 args: build --release" in result.stdout
