from __future__ import annotations

import subprocess
from collections import Counter

from ci_stack import log

SAMPLING_INTERVAL_US = 1000


def start_profile(page):
    cdp = page.context.new_cdp_session(page)
    cdp.send("Profiler.enable")
    cdp.send("Profiler.setSamplingInterval", {"interval": SAMPLING_INTERVAL_US})
    cdp.send("Profiler.start")
    return cdp


def frame_label(node: dict) -> str:
    frame = node["callFrame"]
    source = frame["url"].rsplit("/", 1)[-1].split("?")[0]
    return f"{frame['functionName'] or '(anonymous)'} {source}:{frame['lineNumber'] + 1}"


def log_profile(cdp, top: int = 20) -> None:
    profile = cdp.send("Profiler.stop")["profile"]
    nodes = {node["id"]: node for node in profile["nodes"]}
    self_us: Counter = Counter()
    for node_id, delta in zip(profile["samples"], profile["timeDeltas"]):
        self_us[frame_label(nodes[node_id])] += delta
    total = sum(self_us.values()) or 1
    log(f"main thread profile over {total / 1e6:.0f}s, top self time:")
    for label, us in self_us.most_common(top):
        log(f"  {us / 1e6:7.1f}s {100 * us / total:5.1f}%  {label[:140]}")


def log_busiest_processes(count: int = 10) -> None:
    out = subprocess.run(["ps", "-Ao", "pcpu=,time=,args="], capture_output=True, text=True).stdout
    rows = sorted(out.splitlines(), key=lambda row: float(row.split()[0]), reverse=True)
    log("busiest processes:\n" + "\n".join(row[:150] for row in rows[:count]))
