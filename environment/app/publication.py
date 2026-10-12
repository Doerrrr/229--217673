"""Incomplete generation publisher used by the deployed curation job."""

import json
from pathlib import Path


def publish(root, release_id, expected_parent, artifacts, hook=None):
    root = Path(root)
    destination = root / "releases" / release_id
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (destination / name).write_bytes(payload)
    (root / "CURRENT").write_text(release_id + "\n", encoding="ascii")
    return release_id


def read_current(root):
    root = Path(root)
    if not (root / "CURRENT").exists():
        return None
    release_id = (root / "CURRENT").read_text().strip()
    folder = root / "releases" / release_id
    return {"release_id": release_id, "parent": None,
            "artifacts": {p.name: p.read_bytes() for p in folder.iterdir()}}
