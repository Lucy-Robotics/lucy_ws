"""Guard against spawning ROS nodes through the `ros2` CLI.

`ros2 run` and `ros2 launch` start the real node as a child of themselves, and
on Windows a console-script shim adds another layer. Signalling the handle you
hold then leaves the node running, and capturing its output blocks past the
timeout because the surviving child still holds the pipe. Resolve the
executable and run it directly instead (`node_argv`), or ask the graph with
rclpy rather than `ros2 topic`.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".pixi", "src", "build", "install", "log", "node_modules", ".git", "dist"}

# Deliberate uses, with the reason each one cannot orphan a node or block.
ALLOWED = {
    # Top-level blocking call: launch owns the terminal and its own shutdown.
    ("scripts/pixi_lucy_launch.py", "launch"),
    # Output is inherited, not piped, so nothing can block on a surviving child.
    ("scripts/ros_doctor.py", "doctor"),
}


def _python_files():
    for path in sorted(ROOT.rglob("*.py")):
        if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            yield path


def _ros2_invocations(path: Path):
    """(verb, lineno) for every list literal that starts with "ros2"."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.List) or not node.elts:
            continue
        head = node.elts[0]
        if isinstance(head, ast.Constant) and head.value == "ros2":
            verb = (
                node.elts[1].value
                if len(node.elts) > 1 and isinstance(node.elts[1], ast.Constant)
                else "?"
            )
            yield verb, node.lineno


@pytest.mark.parametrize("path", list(_python_files()), ids=lambda p: str(p.name))
def test_no_unreviewed_ros2_cli_invocation(path):
    rel = path.relative_to(ROOT).as_posix()
    unexpected = [
        f"{rel}:{lineno} builds `ros2 {verb} ...`"
        for verb, lineno in _ros2_invocations(path)
        if (rel, verb) not in ALLOWED
    ]
    assert not unexpected, (
        "\n".join(unexpected)
        + "\n\nThe `ros2` CLI runs the node as its own child, so signalling or "
        "timing out what you hold orphans it. Resolve the executable and run it "
        "directly, or add it to ALLOWED here with the reason it is safe."
    )


def test_allowlist_entries_still_exist():
    """A stale allowlist silently stops guarding."""
    found = {
        (path.relative_to(ROOT).as_posix(), verb)
        for path in _python_files()
        for verb, _ in _ros2_invocations(path)
    }
    assert ALLOWED <= found, f"allowlist no longer matches the code: {ALLOWED - found}"
