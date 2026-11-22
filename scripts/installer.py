#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

REPO_URL = "https://github.com/Lucy-Robotics/lucy_ws.git"
REPO_NAME = "lucy_ws"          # Name of the folder the repo is cloned into.
INSTALL_SCRIPT = "install.py"
DEFAULT_BRANCH = "master"


# ============================================================
# Platform
# ============================================================

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import msvcrt
else:
    import termios
    import tty


# ============================================================
# ANSI colors
# ============================================================

RESET = "\033[0m"

BOLD = "\033[1m"
DIM = "\033[2m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
WHITE = "\033[37m"

BRIGHT_BLACK = "\033[90m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_CYAN = "\033[96m"


# ============================================================
# Terminal state
# ============================================================

_cursor_hidden = False


def enable_ansi():
    """
    Enable ANSI escape sequences on Windows.
    Modern Windows terminals usually support this already.
    """
    if not IS_WINDOWS:
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        stdout_handle = kernel32.GetStdHandle(-11)

        mode = ctypes.c_ulong()

        if kernel32.GetConsoleMode(
            stdout_handle,
            ctypes.byref(mode)
        ):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(
                stdout_handle,
                mode.value | 0x0004
            )

    except Exception:
        pass


def color(text, colour):
    return f"{colour}{text}{RESET}"


def clear_screen():
    print("\033[2J\033[H", end="", flush=True)


def hide_cursor():
    global _cursor_hidden

    if not _cursor_hidden:
        print("\033[?25l", end="", flush=True)
        _cursor_hidden = True


def show_cursor():
    global _cursor_hidden

    print("\033[?25h", end="", flush=True)
    _cursor_hidden = False


# ============================================================
# Header
# ============================================================

def print_header():
    print(color(
        "  ██╗     ██╗   ██╗ ██████╗██╗   ██╗",
        BRIGHT_GREEN
    ))
    print(color(
        "  ██║     ██║   ██║██╔════╝╚██╗ ██╔╝",
        BRIGHT_GREEN
    ))
    print(color(
        "  ██║     ██║   ██║██║      ╚████╔╝ ",
        BRIGHT_GREEN
    ))
    print(color(
        "  ██║     ██║   ██║██║       ╚██╔╝  ",
        BRIGHT_GREEN
    ))
    print(color(
        "  ███████╗╚██████╔╝╚██████╗   ██║   ",
        BRIGHT_GREEN
    ))
    print(color(
        "  ╚══════╝ ╚═════╝  ╚═════╝   ╚═╝   ",
        BRIGHT_GREEN
    ))

    print()

    print(
        color(
            "  LUCY WORKSPACE INSTALLER",
            BOLD + WHITE
        )
    )

    print(
        color(
            "  " + "─" * 42,
            BRIGHT_BLACK
        )
    )

    print()


# ============================================================
# Errors
# ============================================================

def die(message):
    show_cursor()

    print()
    print(
        color("[ ERROR ]", RED),
        message
    )

    sys.exit(1)


# ============================================================
# Dependencies
# ============================================================

def check_dependencies():
    if shutil.which("git") is None:
        die("'git' is required but was not found.")

    # We are already running under Python, so don't need to
    # separately check for python3.


# ============================================================
# Git branch discovery
# ============================================================

def get_branches():
    print(
        color("  [*]", BRIGHT_CYAN),
        "Fetching available branches..."
    )

    result = subprocess.run(
        [
            "git",
            "ls-remote",
            "--heads",
            REPO_URL,
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        error = result.stderr.strip()

        die(
            "Unable to fetch repository branches."
            + (f"\n{error}" if error else "")
        )

    branches = []

    for line in result.stdout.splitlines():
        parts = line.split()

        if len(parts) != 2:
            continue

        ref = parts[1]

        if ref.startswith("refs/heads/"):
            branch = ref[len("refs/heads/"):]

            if branch not in branches:
                branches.append(branch)

    if not branches:
        die("No branches found.")

    # Sort alphabetically.
    branches.sort()

    # Always put master first.
    if DEFAULT_BRANCH in branches:
        branches.remove(DEFAULT_BRANCH)
        branches.insert(0, DEFAULT_BRANCH)

    return branches


# ============================================================
# Keyboard input
# ============================================================

def read_key_windows():
    key = msvcrt.getwch()

    # Windows special keys are returned as:
    # \x00 or \xe0 followed by another character.
    if key in ("\x00", "\xe0"):
        key = msvcrt.getwch()

        if key == "H":
            return "UP"

        if key == "P":
            return "DOWN"

        if key == "K":
            return "LEFT"

        if key == "M":
            return "RIGHT"

    if key in ("\r", "\n"):
        return "ENTER"

    if key.lower() == "q":
        return "QUIT"

    if key == "\x03":
        raise KeyboardInterrupt

    return key


def read_key_unix():
    old_settings = termios.tcgetattr(sys.stdin)

    try:
        tty.setraw(sys.stdin.fileno())

        key = sys.stdin.read(1)

        # Ctrl+C
        if key == "\x03":
            raise KeyboardInterrupt

        # Escape sequence
        if key == "\x1b":
            sequence = sys.stdin.read(2)

            if sequence == "[A":
                return "UP"

            if sequence == "[B":
                return "DOWN"

            if sequence == "[C":
                return "RIGHT"

            if sequence == "[D":
                return "LEFT"

            return "ESC"

        if key in ("\r", "\n"):
            return "ENTER"

        if key.lower() == "q":
            return "QUIT"

        return key

    finally:
        termios.tcsetattr(
            sys.stdin,
            termios.TCSADRAIN,
            old_settings
        )


def read_key():
    if IS_WINDOWS:
        return read_key_windows()

    return read_key_unix()


# ============================================================
# Branch selector
# ============================================================

def select_branch(branches):
    selected = 0

    hide_cursor()

    try:
        while True:
            clear_screen()
            print_header()

            print(
                color(
                    "  Select a branch",
                    BOLD + WHITE
                )
            )

            print()

            for index, branch in enumerate(branches):

                if index == selected:
                    pointer = color(
                        "  >",
                        BRIGHT_GREEN
                    )

                    branch_text = color(
                        branch,
                        BOLD + BRIGHT_GREEN
                    )

                else:
                    pointer = "   "

                    branch_text = color(
                        branch,
                        WHITE
                    )

                if branch == DEFAULT_BRANCH:
                    suffix = color(
                        " [default]",
                        DIM + BRIGHT_BLACK
                    )
                else:
                    suffix = ""

                print(
                    f"{pointer} "
                    f"{branch_text}"
                    f"{suffix}"
                )

            print()

            print(
                color("  UP/DOWN", BRIGHT_CYAN),
                color("navigate", DIM + WHITE),
                " ",
                color("ENTER", BRIGHT_CYAN),
                color("select", DIM + WHITE),
                " ",
                color("Q", BRIGHT_CYAN),
                color("quit", DIM + WHITE),
            )

            key = read_key()

            if key == "UP":
                selected = (
                    selected - 1
                ) % len(branches)

            elif key == "DOWN":
                selected = (
                    selected + 1
                ) % len(branches)

            elif key == "ENTER":
                return branches[selected]

            elif key == "QUIT":
                return None

    finally:
        show_cursor()


# ============================================================
# Installation
# ============================================================

def install(branch):
    clear_screen()
    print_header()

    # The repo is cloned into a subfolder (REPO_NAME) of the
    # directory where the installer was launched, rather than
    # directly into that directory.
    base_dir = Path.cwd().resolve()
    install_dir = base_dir / REPO_NAME

    print(
        color(
            "  Installation",
            BOLD + WHITE
        )
    )

    print()

    print(
        color("  Repository  ", BRIGHT_BLACK),
        REPO_URL
    )

    print(
        color("  Branch      ", BRIGHT_BLACK),
        color(branch, BRIGHT_GREEN)
    )

    print(
        color("  Location    ", BRIGHT_BLACK),
        str(install_dir)
    )

    print()

    print(
        color(
            "  " + "─" * 42,
            BRIGHT_BLACK
        )
    )

    print()

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    # git clone requires the destination directory to not
    # already exist (or to be empty). We explicitly check this
    # up front to avoid accidentally clashing with an existing
    # project and to give a clear error message.
    if install_dir.exists():
        if any(install_dir.iterdir()):
            die(
                "The installation directory is not empty:\n"
                f"  {install_dir}\n\n"
                "Please remove it or choose a different location."
            )
    else:
        try:
            install_dir.mkdir(parents=True)
        except OSError as exc:
            die(
                f"Unable to create installation directory:\n{exc}"
            )

    # --------------------------------------------------------
    # Clone
    # --------------------------------------------------------

    print(
        color("  [1/2]", BRIGHT_CYAN),
        "Cloning repository..."
    )

    result = subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            branch,
            "--single-branch",
            REPO_URL,
            str(install_dir),
        ]
    )

    if result.returncode != 0:
        die("Git clone failed.")

    print()

    print(
        color("  [ OK ]", BRIGHT_GREEN),
        "Repository cloned."
    )

    # --------------------------------------------------------
    # Run install.py from the cloned workspace
    # --------------------------------------------------------

    install_script = install_dir / INSTALL_SCRIPT

    if not install_script.exists():
        die(
            f"'{INSTALL_SCRIPT}' was not found "
            f"in branch '{branch}'."
        )

    print()

    print(
        color("  [2/2]", BRIGHT_CYAN),
        "Running installation script..."
    )

    print()

    print(
        color(
            "  " + "─" * 42,
            BRIGHT_BLACK
        )
    )

    print()

    result = subprocess.run(
        [
            sys.executable,
            str(install_script),
        ],
        cwd=str(install_dir),
    )

    print()

    if result.returncode != 0:
        die(
            "Installation script failed "
            f"with exit code {result.returncode}."
        )

    # --------------------------------------------------------
    # Done
    # --------------------------------------------------------

    print(
        color(
            "  " + "─" * 42,
            BRIGHT_BLACK
        )
    )

    print()

    print(
        color("  [ OK ]", BRIGHT_GREEN),
        color(
            "Installation complete.",
            BOLD + GREEN
        )
    )

    print()

    print(
        color("  Installed to ", BRIGHT_BLACK),
        str(install_dir)
    )

    print()


# ============================================================
# Main
# ============================================================

def main():
    enable_ansi()

    if not sys.stdin.isatty():
        die(
            "This installer requires an interactive terminal."
        )

    check_dependencies()

    clear_screen()
    print_header()

    branches = get_branches()

    print()

    print(
        color("  [ OK ]", BRIGHT_GREEN),
        f"Found {len(branches)} branch(es)."
    )

    print()

    input(
        color(
            "  Press ENTER to continue...",
            DIM + WHITE
        )
    )

    branch = select_branch(branches)

    if branch is None:
        clear_screen()

        print(
            color(
                "\n  Installation cancelled.\n",
                YELLOW
            )
        )

        return

    install(branch)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        show_cursor()

        print(
            color(
                "\n\n  Installation cancelled.",
                YELLOW
            )
        )

        print()

        # Standard Unix convention for SIGINT.
        sys.exit(130)

    except Exception as exc:
        show_cursor()

        print(
            color(
                f"\n  Unexpected error: {exc}",
                RED
            )
        )

        print()

        sys.exit(1)

    finally:
        show_cursor()
