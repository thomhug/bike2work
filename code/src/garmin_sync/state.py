"""Sync state persistence."""
from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2))


def last_activity_id(path: Path) -> int | None:
    s = load(path)
    v = s.get("last_activity_id")
    return int(v) if v is not None else None


def update_last(path: Path, activity_id: int) -> None:
    s = load(path)
    cur = s.get("last_activity_id")
    if cur is None or activity_id > int(cur):
        s["last_activity_id"] = activity_id
        save(path, s)
