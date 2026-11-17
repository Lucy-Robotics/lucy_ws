"""What the TUI starts by itself when it opens."""

from .apply import apply_changes, default_robot_selection
from .choices import settle_selection
from .config import load_selection, save_selection

PRODUCTION_SERVICES = ("core", "control_panel")


def autostart(state, dev_mode):
    """Apply the launch selection on open; return the status line to show, or None."""
    resumes_saved = dev_mode and load_selection() is not None
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
