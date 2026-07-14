"""Snapshot user-editable reminder bodies before a destructive list delete.

Hiding a project deletes its list, which destroys `<bb:notes>` (the one
user-owned region). Per CLAUDE.md → Design stance, the guard against fire-and-
forget destruction is reversibility, not a confirm handshake: write the list's
reminders to a timestamped JSON file first so the notes are recoverable. A hide
proceeds only if the snapshot succeeded (or the list was already empty).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import reminders as reminders_module

SNAP_DIR = Path("~/.claude/reminders-bridge-snapshots").expanduser()


def snapshot_list(list_name: str, reason: str) -> Path | None:
    """Write the list's reminders to a timestamped file. None if nothing to save.

    Raises on write failure — callers should treat that as "do not delete yet".
    """
    reminders = reminders_module.list_reminders(list_name)
    if not reminders:
        return None
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = list_name.replace("/", "_")
    path = SNAP_DIR / f"{safe}-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "list": list_name,
                "reason": reason,
                "at": stamp,
                "reminders": [
                    {"name": r.name, "body": r.body, "completed": r.completed}
                    for r in reminders
                ],
            },
            indent=2,
        )
    )
    return path
