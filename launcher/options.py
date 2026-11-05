"""Launch options: a pick-one list under a package row, appended to its command."""

import json

from .constants import OPTIONS_FILE


def launched_options():
    try:
        return set(json.loads(OPTIONS_FILE.read_text()))
    except (OSError, ValueError):
        return set()


def options_of(state, pkg):
    return [p for p in state.packages if p.parent == pkg.id]


def with_options(pkg, state):
    args = [o.command for o in options_of(state, pkg) if o.selected]
    return " ".join([pkg.command, *args])


def options_changed(state, pkg):
    return any(o.selected != o.is_running for o in options_of(state, pkg))


def record_launch(state, pkg):
    options = options_of(state, pkg)
    launched = launched_options() - {o.id for o in options}
    launched |= {o.id for o in options if o.selected}
    try:
        OPTIONS_FILE.write_text(json.dumps(sorted(launched)))
    except OSError:
        pass
    for option in options:
        option.is_running = option.selected


def default_options(state):
    """Tick the default option of any package that has none ticked."""
    for parent in {p.parent for p in state.packages if p.parent}:
        options = [p for p in state.packages if p.parent == parent]
        if not any(o.selected for o in options):
            for option in options:
                option.selected = option.default_on


def with_focused_options(items, packages, focused_id):
    """Each item, followed by its options while the cursor is on it or on one of them."""
    rows = []
    for item in items:
        rows.append(item)
        options = [p for p in packages if p.parent == item.id]
        if focused_id in {item.id, *(o.id for o in options)}:
            rows += options
    return rows
