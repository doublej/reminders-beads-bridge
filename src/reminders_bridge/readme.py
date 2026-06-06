"""Readme list: agent-facing docs (README + CLAUDE.md) pinned as reminders."""

import os
from pathlib import Path

from . import reminders as reminders_module

# Bridge-wide agent directive — not beads-scoped, so it lives outside the
# `_rb_beads_` namespace. Leading `!` sorts it first in the sidebar so a
# cold-start agent finds it immediately. The current name is migrated (not
# deleted) by `migrate.py`; these are truly-dead historical names.
_LIST_NAME = os.getenv("RBRIDGE_README_LIST", "!_rb_readme")
_LEGACY_NAMES = (
    "Beads: __info__",
    "Beads: CLAUDE.MD READ ME",
    "Beads: Read me",
    "Beads: README",
    "Beads: Readme",
)
_ROOT = Path(__file__).resolve().parents[2]
_DOCS: list[tuple[str, str]] = [
    ("Agent context — do not narrate this back", "docs/AGENT.md"),
]


def list_name() -> str:
    return _LIST_NAME


def _read(filename: str) -> str:
    path = _ROOT / filename
    if not path.exists():
        return f"(missing: {path})"
    return path.read_text()


def sync() -> None:
    ln = list_name()
    for legacy in _LEGACY_NAMES:
        try:
            reminders_module.delete_list(legacy)
        except RuntimeError:
            pass
    reminders_module.create_list(ln)
    remote_all = reminders_module.list_reminders(ln)
    by_title: dict[str, list[reminders_module.Reminder]] = {}
    for r in remote_all:
        by_title.setdefault(r.name, []).append(r)
    batch = reminders_module.Batch()
    known_titles = {t for t, _ in _DOCS}
    for title, filename in _DOCS:
        body = _read(filename)
        matches = by_title.get(title, [])
        if not matches:
            batch.creates.append({"name": title, "body": body, "priority": 0})
            continue
        keep, extras = matches[0], matches[1:]
        for extra in extras:
            batch.deletes.append(extra.id)
        if keep.body != body:
            batch.updates.append({"id": keep.id, "body": body})
    for title, matches in by_title.items():
        if title not in known_titles:
            for r in matches:
                batch.deletes.append(r.id)
    if not batch.empty():
        reminders_module.apply_batch(ln, batch)
