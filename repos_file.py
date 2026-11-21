from __future__ import annotations

import json
from pathlib import Path


def local_path(root) -> Path:
    return Path(root) / "config" / "repos.json.local"


def catalog_path(root) -> Path:
    return Path(root) / "config" / "repos.json"


def active_path(root) -> Path:
    local = local_path(root)
    return local if local.exists() else catalog_path(root)


def read(root) -> dict:
    return json.loads(active_path(root).read_text(encoding="utf-8"))


def write(root, data: dict) -> None:
    temporary = local_path(root).with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(local_path(root))


def enabled(root) -> dict[str, bool]:
    try:
        rows = read(root).get("repos", [])
    except (OSError, ValueError, AttributeError):
        return {}
    return {row.get("name"): row["enabled"] for row in rows
            if row.get("name") and isinstance(row.get("enabled"), bool)}


def _catalog(root) -> dict[str, dict]:
    path = catalog_path(root)
    rows = json.loads(path.read_text(encoding="utf-8"))["repos"] if path.is_file() else []
    return {row.get("name"): row for row in rows}


def set_enabled(root, wanted: dict[str, bool]) -> None:
    data = read(root)
    rows = {row.get("name"): row for row in data["repos"]}
    catalog = _catalog(root)
    for name, on in wanted.items():
        if name not in rows and name in catalog:
            rows[name] = catalog[name]
            data["repos"].append(rows[name])
        if name in rows:
            rows[name]["enabled"] = on
    write(root, data)
