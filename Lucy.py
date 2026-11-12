#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
import shutil

try:
    import curses
except ImportError:  # Windows: handled by windows_main
    curses = None

ESCAPE_DELAY_MS = 50

MIN_TERM_HEIGHT = 15
MIN_TERM_WIDTH = 40
INSTALL_ENV = {"LUCY_PIXI_AUTO_UPGRADE": "1"}

def is_installed():
    """True when the workspace has been built (mirrors launch_lucy.sh's check)."""
    return any(os.path.isfile(f) for f in ("install/setup.bash", "install/setup.bat"))

def get_dev_mode():
    if not os.path.exists(".env"):
        return False
    with open(".env", "r") as f:
        for line in f:
            if line.strip().startswith("DEV="):
                return line.strip().split("=")[1].lower() == "true"
    return False

def set_dev_mode(is_enabled):
    lines = []
    dev_found = False
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()

    with open(".env", "w") as f:
        for line in lines:
            if line.strip().startswith("DEV="):
                f.write(f"DEV={str(is_enabled).lower()}\n")
                dev_found = True
            else:
                f.write(line)
        if not dev_found:
            f.write(f"DEV={str(is_enabled).lower()}\n")

PIXI_TASKS = (
    ("pixi run core", "robot stack + rosbridge on 9090"),
    ("pixi run control-panel", "web UI on http://localhost:4004"),
    ("pixi run rviz", "optional viewer"),
)


def ws_session(value):
    """`-ws 2` or `-ws lucy_ws_2` -> lucy_ws_2: the Control Center instance to use.

    The number shifts the instance's ports (launch_lucy.sh), so it is required."""
    match = re.fullmatch(r"(?:lucy_ws_)?(\d+)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"expected N or lucy_ws_N, got {value!r}")
    return f"lucy_ws_{int(match.group(1))}"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Lucy workspace manager")
    parser.add_argument(
        "-ws", "--ws", type=ws_session, metavar="N",
        help="Control Center instance to launch or join (lucy_ws_N, ports shifted by N); "
        "default: lucy_ws_0, or the next free one",
    )
    return parser.parse_args(argv)


def confirm(prompt):
    """Yes unless explicitly declined; assumes yes when nothing can answer."""
    if not sys.stdin.isatty():
        return True
    try:
        return input(f"{prompt} [Y/n] ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return True


def windows_main():
    """Entry point on Windows, which has neither curses for the TUI nor tmux to drive.

    Lucy-Setup.exe is the supported installer; this covers running Lucy.py directly.
    """
    if not is_installed():
        print("Lucy is not installed in this workspace. Running install.py")
        rc = run_command([sys.executable, "install.py"], extra_env=INSTALL_ENV)
        if rc != 0:
            print(f"\nInstall failed with exit code {rc}.", file=sys.stderr)
            return rc

    print("\nLucy is installed. Start each component in its own terminal:")
    for command, purpose in PIXI_TASKS:
        print(f"  {command:<24} {purpose}")
    return 0


def prepend_pixi_to_path():
    """Prefer ~/.pixi/bin over system/nix pixi (official installer is usually newer)."""
    pixi_bin = os.path.join(os.path.expanduser("~"), ".pixi", "bin")
    if os.path.isdir(pixi_bin):
        path = os.environ.get("PATH", "")
        parts = path.split(os.pathsep) if path else []
        if pixi_bin not in parts:
            os.environ["PATH"] = pixi_bin + os.pathsep + path

def check_prereqs():
    prepend_pixi_to_path()
    if shutil.which("pixi") is None:
        print("Missing pixi. Install: https://pixi.prefix.dev/latest/installation/")
        return False
    return True

def run_command(command, extra_env=None):
    """Runs a command with standard IO inherited.

    The child keeps the real terminal, so its output is not block-buffered, git
    and pixi report progress, and credential prompts reach the user.
    """
    print(f"--- Running: {' '.join(command)} ---")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        return subprocess.run(command, env=env).returncode
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Make sure it's in your PATH and executable.")
        return -1
    except Exception as e:
        print(f"An error occurred: {e}")
        return -1

def use_responsive_escape():
    """ESC starts every arrow and function key sequence, so ncurses delays
    reporting a lone ESC. Call after curses is initialised."""
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(ESCAPE_DELAY_MS)


def not_installed_screen(stdscr):
    """First-run screen shown when the workspace isn't built yet.
    Returns True to install, False to close. (Terminal size is guaranteed by the
    pre-check in __main__.)"""
    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    use_responsive_escape()

    is_dev_mode = get_dev_mode()

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Lucy Workspace Manager"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)

        lines = [
            ("Lucy is not installed on this machine.", curses.A_BOLD),
            ("", curses.A_NORMAL),
        ]
        start = max(2, h // 2 - len(lines) // 2)
        for i, (text, attr) in enumerate(lines):
            stdscr.addstr(start + i, max(0, (w - len(text)) // 2), text, attr)

        checkbox = "[x]" if is_dev_mode else "[ ]"
        dev_line = f"{checkbox} Developer Mode"
        stdscr.addstr(start + len(lines), max(0, (w - len(dev_line)) // 2), dev_line)
        hint_line = "(installs over SSH; Launch unchanged)"
        stdscr.addstr(start + len(lines) + 1, max(0, (w - len(hint_line)) // 2), hint_line, curses.A_DIM)

        footer = [
            ("", curses.A_NORMAL),
            ("Press ENTER to install", curses.A_NORMAL),
            ("Press Q or ESC to close", curses.A_DIM),
        ]
        for i, (text, attr) in enumerate(footer):
            stdscr.addstr(start + len(lines) + 3 + i, max(0, (w - len(text)) // 2), text, attr)

        stdscr.addstr(h - 2, 2, "Space: Toggle Developer Mode", curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord('\n'), ord('\r')):
            set_dev_mode(is_dev_mode)
            return True
        if key in (ord('q'), ord('Q'), 27):  # q / ESC
            return False
        if key == ord(' '):
            is_dev_mode = not is_dev_mode
            set_dev_mode(is_dev_mode)

def main_tui(stdscr):
    """The main curses TUI function. Returns the command to run."""
    h, w = stdscr.getmaxyx()
    if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
        return "TerminalTooSmall"

    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    use_responsive_escape()
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)

    is_dev_mode = get_dev_mode()
    current_idx = 0
    options = ["Launch", "---", "Update", "Rebuild", "Exit", "---", "Developer Mode"]
    ws = os.environ.get("LUCY_TMUX_SESSION")

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = f"Lucy Workspace Manager ({ws})" if ws else "Lucy Workspace Manager"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)

        for i, option in enumerate(options):
            if option == "---":
                stdscr.addstr(2 + i, 4, "----------------------")
                continue

            prefix = "> " if current_idx == i else "  "

            if option == "Developer Mode":
                checkbox = "[x]" if is_dev_mode else "[ ]"
                stdscr.addstr(2 + i, 4, f"{prefix}{checkbox} {option}")
            else:
                stdscr.addstr(2 + i, 4, f"{prefix}{option}")

        stdscr.refresh()

        key = stdscr.getch()

        if key in (ord('q'), ord('Q'), ord('x'), ord('X'), 27):  # q / x / ESC
            return None

        if key == curses.KEY_UP:
            current_idx = (current_idx - 1 + len(options)) % len(options)
            if options[current_idx] == "---":
                current_idx = (current_idx - 1 + len(options)) % len(options)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(options)
            if options[current_idx] == "---":
                current_idx = (current_idx + 1) % len(options)
        elif key in [ord(' '), ord('\n')]:
            selected_option = options[current_idx]

            if selected_option == "Developer Mode":
                is_dev_mode = not is_dev_mode
                set_dev_mode(is_dev_mode)
            elif selected_option == "Update":
                return {
                    "cmd": [sys.executable, "install.py"],
                    "name": "Install",
                    "extra_env": INSTALL_ENV,
                }
            elif selected_option == "Rebuild":
                return {
                    "cmd": ["pixi", "run", "build"],
                    "name": "Rebuild",
                    "followup": [["pixi", "run", "panel-install"]]
                    + ([] if is_dev_mode else [["pixi", "run", "panel-build"]]),
                }
            elif selected_option == "Launch":
                # Hands the terminal to the stack; the menu does not come back.
                return {"cmd": ["./launch_lucy.sh"], "name": "Launch", "exits_menu": True}
            elif selected_option == "Exit":
                return None

if __name__ == "__main__":
    args = parse_args()
    if args.ws:
        # launch_lucy.sh pins this session instead of picking the next free one.
        os.environ["LUCY_TMUX_SESSION"] = args.ws

    # This initial check is done before curses.wrapper to provide a clean error message
    # without the screen flicker of initializing and de-initializing curses.
    # Windows first: the size check below needs curses, which does not exist there.
    if sys.platform == "win32":
        sys.exit(windows_main())

    def check_initial_size():
        stdscr = curses.initscr()
        h, w = stdscr.getmaxyx()
        curses.endwin()
        return h >= MIN_TERM_HEIGHT and w >= MIN_TERM_WIDTH

    if not check_initial_size():
        print("Error: Terminal window is too small.", file=sys.stderr)
        print(f"Please increase the terminal size to at least {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} characters.", file=sys.stderr)
        sys.exit(1)

    # First run: nothing built yet — offer to install before showing the menu.
    if not is_installed():
        try:
            wants_install = curses.wrapper(not_installed_screen)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        except curses.error as e:
            print(f"A terminal error occurred: {e}", file=sys.stderr)
            print("This might be due to resizing the window. Please restart.", file=sys.stderr)
            sys.exit(1)
        if not wants_install:
            sys.exit(0)
        rc = run_command([sys.executable, "install.py"], extra_env=INSTALL_ENV)
        if rc != 0:
            print(f"\n--- Install finished with exit code {rc} ---")
            print("Press Enter to exit.")
            input()
            sys.exit(rc)
        print("\n--- Install finished successfully. ---")
        print("Press Enter to continue to the menu.")
        input()

    if not check_prereqs():
        sys.exit(1)

    while True:
        task = None
        try:
            task = curses.wrapper(main_tui)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        except curses.error as e:
            print(f"A terminal error occurred: {e}", file=sys.stderr)
            print("This might be due to resizing the window. Please restart.", file=sys.stderr)
            sys.exit(1)

        if isinstance(task, str) and task == "TerminalTooSmall":
             # This case is handled by the pre-check, but as a fallback.
            print("Error: Terminal window is too small.", file=sys.stderr)
            print(f"Please increase the terminal size to at least {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} characters.", file=sys.stderr)
            sys.exit(1)

        if not task:
            # User selected Exit
            break

        rc = run_command(task["cmd"], extra_env=task.get("extra_env"))
        for follow in task.get("followup", []):
            if rc != 0:
                break
            rc = run_command(follow, extra_env=task.get("extra_env"))

        if task.get("exits_menu", False):
            print(f"--- Session finished with exit code {rc} ---")
            break

        task_name = task.get("name")
        if task_name in ["Install", "Rebuild"] and rc == 0:
            print(f"\n--- Task '{task_name}' finished successfully. ---")
            print("Press Enter to return to the menu.")
            input()
        else:
            print(f"\n--- Task '{task_name}' finished with exit code {rc} ---")
            print("Press Enter to exit.")
            input()
            break

    sys.exit(0)
