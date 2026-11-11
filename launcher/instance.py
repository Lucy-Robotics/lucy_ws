"""Several Control Centers on one host, one per tmux session.

launch_lucy.sh starts a second launcher in its own session (lucy_ws_1, ...)
when lucy_ws is already shown in a terminal. Each instance keeps its own
launcher files (constants.instance_suffix), and its stack is told apart from the
others by LUCY_TMUX_SESSION in the environment of every process it starts.

Instances must not share a ROS domain, or their graphs merge: each one claims
the domains it uses in its pidfile ("<pid>\\n<domain> <domain>..."), and the
others skip them.
"""

import os
import re
import tempfile

from .constants import (
    DEFAULT_TMUX_SESSION,
    LAUNCHER_PIDFILE,
    TMUX_SESSION,
    WORKSPACE_ROOT,
)

_PIDFILE_RE = re.compile(r"^\.lucy_launcher(?:\.(?P<session>.+))?\.pid$")


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # alive, owned by someone else
    return True


def read_pidfile(path):
    """(pid, claimed domains) from a launcher pidfile, or (None, set())."""
    try:
        lines = path.read_text().splitlines()
        pid = int(lines[0].strip())
    except (OSError, ValueError, IndexError):
        return None, set()
    domains = set()
    for token in (lines[1] if len(lines) > 1 else "").split():
        if token.isdigit():
            domains.add(int(token))
    return pid, domains


def other_instance_domains(root=WORKSPACE_ROOT, own_session=TMUX_SESSION):
    """ROS domains claimed by the other live Control Centers of this workspace."""
    taken = set()
    for path in root.glob(".lucy_launcher*.pid"):
        match = _PIDFILE_RE.match(path.name)
        if not match:
            continue
        if (match.group("session") or DEFAULT_TMUX_SESSION) == own_session:
            continue
        pid, domains = read_pidfile(path)
        if pid is not None and pid != os.getpid() and _pid_alive(pid):
            taken |= domains
    return taken


def claim_domains(domains, pidfile=LAUNCHER_PIDFILE):
    """Write this launcher's pidfile: its pid, then the domains it uses."""
    claimed = " ".join(map(str, sorted(domains)))
    try:
        pidfile.write_text(f"{os.getpid()}\n{claimed}\n")
    except OSError:
        pass


def export_instance_env(session=TMUX_SESSION, environ=os.environ):
    """Per-instance settings a second instance needs before anything starts.

    The default instance keeps the stock values, so a single Control Center
    behaves as it always has."""
    environ["LUCY_TMUX_SESSION"] = session
    if session == DEFAULT_TMUX_SESSION:
        return
    tmp = tempfile.gettempdir()
    uid = os.getuid() if hasattr(os, "getuid") else 0
    # Gazebo transport is not scoped by the ROS domain: two simulators on one
    # host would otherwise exchange clock and joint topics.
    environ.setdefault("GZ_PARTITION", session)
    # Ready markers the readiness checks read (supervisor, lucy_cli).
    environ.setdefault(
        "LUCY_CONTROL_READY_FILE", os.path.join(tmp, f"lucy_control_ready.{uid}.{session}")
    )
    environ.setdefault("LUCY_CLI_READY_FILE", os.path.join(tmp, f"lucy_cli.{session}.ready"))


def process_session(environ):
    """The instance a process belongs to, from its environment.

    First token only: the macOS reader (ps eww) runs a value on to the next
    variable it knows about, and session names have no spaces."""
    value = (environ.get("LUCY_TMUX_SESSION") or "").split()
    return value[0] if value else DEFAULT_TMUX_SESSION
