import subprocess


def copied_message():
    copied = subprocess.run(
        ["tmux", "show-buffer"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    chars = "char" if len(copied) == 1 else "chars"
    return f"Copied {len(copied)} {chars} to clipboard"
