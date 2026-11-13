"""ROS domain the launcher runs the stack in (lucy.launch.py's domain_id:=)."""

import os

# lucy.launch.py's MAX_DOMAIN_ID: above it, DDS ports overflow on Linux.
MAX_DOMAIN_ID = 101


def parse_domain_id(value):
    """The domain id in `value`, or None when it is not one lucy.launch.py accepts."""
    try:
        domain = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return domain if 0 <= domain <= MAX_DOMAIN_ID else None


def env_domain_id():
    """ROS_DOMAIN_ID from the launcher's environment (.env included), else 0."""
    domain = parse_domain_id(os.environ.get("ROS_DOMAIN_ID", ""))
    return 0 if domain is None else domain


def step_domain_id(domain, delta):
    """`domain` moved by `delta`, held within 0..MAX_DOMAIN_ID."""
    return min(MAX_DOMAIN_ID, max(0, domain + delta))


def export_domain_id(domain):
    """Make `domain` the launcher's ROS_DOMAIN_ID.

    Readiness checks inherit it, and tmux windows get it through INSTANCE_ENV_KEYS."""
    os.environ["ROS_DOMAIN_ID"] = str(domain)
