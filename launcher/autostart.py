"""What the TUI starts by itself when it opens."""

from .apply import apply_changes, default_robot_selection
from .choices import settle_selection
from .config import load_selection, save_selection

PRODUCTION_SERVICES = ("core", "control_panel")


def has_saved_launch(state):
    saved = load_selection() or set()
    return any(p.id in saved and p.type != "option" for p in state.packages)


def autostart(state, dev_mode):
    """Apply the launch selection on open; return the status line to show, or None."""
    resumes_saved = dev_mode and has_saved_launch(state)
    if not resumes_saved:
        for pkg_id in PRODUCTION_SERVICES:
            pkg = state.get_by_id(pkg_id)
            if pkg:
                pkg.selected = True
        default_robot_selection(state)
        settle_selection(state)
    selected = {p.id for p in state.packages if p.selected}
    if not selected:
        return None
    apply_changes(state)
    save_selection(selected, state.domain_id)
    if resumes_saved:
        return "Starting your saved launch configuration..."
    if dev_mode:
        return "Starting default services..."
    return "Starting default services for production mode..."
