"""The URLs a package can be opened at, as listed on its row in the TUI."""

import functools
import ipaddress
import socket

from .options import options_of
from .state import _status_url

CONTAINER_BRIDGES = ipaddress.ip_network("172.16.0.0/12")


def _default_route_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
        except OSError:
            return []
        return [probe.getsockname()[0]]


def _hostname_ips():
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return [info[4][0] for info in infos]


def reachable(ip):
    address = ipaddress.ip_address(ip)
    return not address.is_loopback and address not in CONTAINER_BRIDGES


@functools.cache
def network_ips():
    return [ip for ip in dict.fromkeys(_default_route_ip() + _hostname_ips()) if reachable(ip)]


def access_urls(pkg, state):
    url = _status_url(pkg)
    if not url:
        return []
    if not any("0.0.0.0" in o.command and o.is_running for o in options_of(state, pkg)):
        return [url]
    return [url, *(url.replace("localhost", ip) for ip in network_ips())]


def fit_urls(urls, room):
    """As many URLs as fit in `room` columns, left to right, as one " (a  b)" label."""
    label = ""
    for count in range(1, len(urls) + 1):
        candidate = f" ({'  '.join(urls[:count])})"
        if len(candidate) > room:
            break
        label = candidate
    return label
