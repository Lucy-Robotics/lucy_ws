def same_choice(pkg, other):
    return bool(pkg.choice) and pkg is not other and other.choice == pkg.choice


def is_last_choice(state, pkg):
    return bool(pkg.choice) and not any(
        other.selected for other in state.packages if same_choice(pkg, other)
    )


def _deps_selected(state, pkg):
    return all(
        state.get_by_id(dep) and state.get_by_id(dep).selected
        for dep in pkg.dependencies
    )


def settle_selection(state):
    for pkg in state.packages:
        if pkg.selected and not _deps_selected(state, pkg):
            pkg.selected = False
    groups = dict.fromkeys(p.choice for p in state.packages if p.choice)
    for group in groups:
        members = [p for p in state.packages if p.choice == group]
        if any(p.selected for p in members):
            continue
        ready = [p for p in members if _deps_selected(state, p)]
        if ready:
            ready[0].selected = True
