from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

COMMAND_LINE_TOOLS_DIR = "/Library/Developer/CommandLineTools"
PROBE_SOURCE = '#include <unistd.h>\nint main(void) { return (int)write(1, "", 0); }\n'


def pixi_links_c(project_root: Path | str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "probe.c"
        source.write_text(PROBE_SOURCE)
        try:
            result = subprocess.run(
                ["pixi", "run", "sh", "-c", 'cc $LDFLAGS "$0" -o "$1"', str(source), str(Path(tmp) / "probe")],
                cwd=str(project_root), capture_output=True, text=True, timeout=300, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        return result.returncode == 0


def active_sdk() -> str:
    try:
        result = subprocess.run(
            ["xcrun", "--show-sdk-path"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def command_line_tools_installed() -> bool:
    return Path(COMMAND_LINE_TOOLS_DIR).is_dir()


def unreadable_sdk_help(sdk: str) -> str:
    return (
        f"The Pixi linker cannot read the macOS SDK {sdk}, it is newer than the conda-forge "
        "toolchain supports. Install or update the Command Line Tools (xcode-select --install), "
        f"select them with 'sudo xcode-select -s {COMMAND_LINE_TOOLS_DIR}', then re-run the "
        "installer. Undo later with 'sudo xcode-select -r'."
    )
