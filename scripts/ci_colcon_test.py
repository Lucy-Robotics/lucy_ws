#!/usr/bin/env python3
"""
CI-friendly colcon test.

Features:
- Stable package skips.
- Automatically skips thais_urdf when present.
- Disables pytest plugin autoloading.
- Forwards additional arguments to colcon test.
- Dumps colcon test results on failure.
- Dumps relevant failed test logs on failure.
- Works natively on Windows, Linux, and macOS.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

BASE_SKIP = [
    "lucy_cli",
    "lucy_config_pipeline",
    "lucy_control_supervisor",
    "camera_ros",
]

FAILURE_PATTERN = re.compile(
    r"FAILED|ERROR|Failed|Traceback|NO TESTS RAN"
)

CTEST_FAILURE_PATTERN = re.compile(
    r"Failed|FAILED"
)


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command while preserving its output."""
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        text=True,
    )


def get_skipped_packages() -> list[str]:
    """Return packages that should be excluded from testing."""
    skip = list(BASE_SKIP)

    if (ROOT / "src" / "thais_urdf").is_dir():
        skip.append("thais_urdf")

    return skip


def get_tested_packages(skip: list[str]) -> list[str]:
    """Return the package names that colcon would test."""
    command = [
        "colcon",
        "list",
        "--names-only",
        "--packages-skip",
        *skip,
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def tail_file(path: Path, lines: int) -> None:
    """Print the last N lines of a text file."""
    try:
        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return

    tail = content.splitlines()[-lines:]

    for line in tail:
        print(line)


def contains_pattern(path: Path, pattern: re.Pattern[str]) -> bool:
    """Return True if a file contains the supplied regex."""
    try:
        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return False

    return bool(pattern.search(content))


def dump_failure_logs(skip: list[str]) -> None:
    """Dump colcon test results and relevant failure logs."""

    tested = get_tested_packages(skip)

    print("::group::colcon test-result")

    if tested:
        command = [
            "colcon",
            "test-result",
            "--verbose",
            "--packages-select",
            *tested,
        ]
    else:
        command = [
            "colcon",
            "test-result",
            "--verbose",
        ]

    subprocess.run(
        command,
        cwd=ROOT,
        check=False,
    )

    print("::endgroup::")

    print("::group::Failed test logs")

    log_dir = ROOT / "log"

    if log_dir.is_dir():
        for path in log_dir.rglob("*"):
            if not path.is_file():
                continue

            if path.name not in {"stdout.log", "stderr.log"}:
                continue

            # Match the original:
            # */test_*/*
            try:
                relative = path.relative_to(log_dir)
            except ValueError:
                continue

            if not any(part.startswith("test_") for part in relative.parts):
                continue

            if contains_pattern(path, FAILURE_PATTERN):
                print(f"--- {path} ---")
                tail_file(path, 120)

    # Match:
    # build/*/Testing/Temporary/LastTest.log
    build_dir = ROOT / "build"

    if build_dir.is_dir():
        for path in build_dir.glob("*/Testing/Temporary/LastTest.log"):
            if contains_pattern(path, CTEST_FAILURE_PATTERN):
                print(f"--- {path} ---")
                tail_file(path, 80)

    print("::endgroup::")


def main() -> int:
    os.chdir(ROOT)

    # Disable pytest's automatic third-party plugin discovery.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    skip = get_skipped_packages()

    args = [
        "colcon",
        "test",
        "--return-code-on-test-failure",
        "--packages-skip",
        *skip,
        *sys.argv[1:],
    ]

    result = run(args)

    if result.returncode != 0:
        dump_failure_logs(skip)

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
