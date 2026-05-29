"""Settings list: one reminder per toggle. Completed = enabled.

The list is bridge-global (restart, poll interval, display toggles), so it lives
under the `rbridge:` namespace rather than the beads `{prefix}` — overridable via
RBRIDGE_SETTINGS_LIST. The pre-rename `{prefix}Settings` list is deleted on sync.
"""

import os
from dataclasses import dataclass

from . import reminders as reminders_module

_LIST_NAME = os.getenv("RBRIDGE_SETTINGS_LIST", "rbridge: Settings")


@dataclass(frozen=True)
class Setting:
    key: str
    title: str
    body: str
    default: bool = False


SETTINGS: tuple[Setting, ...] = (
    Setting(
        key="show_completed",
        title="Show completed tasks",
        body=(
            "Check to also show closed beads as completed reminders in each "
            "project list. Uncheck to keep project lists focused on open and "
            "in-progress work (closed beads are pruned)."
        ),
    ),
)


def list_name() -> str:
    return _LIST_NAME


def _delete_legacy(prefix: str) -> None:
    for legacy in (f"{prefix}Settings", "Beads: Settings"):
        if legacy == _LIST_NAME:
            continue
        try:
            reminders_module.delete_list(legacy)
        except RuntimeError:
            pass


def defaults() -> dict[str, bool]:
    return {s.key: s.default for s in SETTINGS}


def sync(prefix: str) -> dict[str, bool]:
    """Reconcile settings list. Return {key: enabled} for every known setting."""
    ln = list_name()
    _delete_legacy(prefix)
    reminders_module.create_list(ln)
    remote = reminders_module.list_reminders(ln)
    by_name: dict[str, list[reminders_module.Reminder]] = {}
    for r in remote:
        by_name.setdefault(r.name, []).append(r)

    values = defaults()
    expected = {s.title for s in SETTINGS}
    batch = reminders_module.Batch()

    for s in SETTINGS:
        matches = by_name.get(s.title, [])
        if not matches:
            batch.creates.append({"name": s.title, "body": s.body, "priority": 0})
            continue
        keep, extras = matches[0], matches[1:]
        for extra in extras:
            batch.deletes.append(extra.id)
        values[s.key] = bool(keep.completed)
        if keep.body != s.body:
            batch.updates.append({"id": keep.id, "body": s.body})

    for name, matches in by_name.items():
        if name in expected:
            continue
        for r in matches:
            batch.deletes.append(r.id)

    if not batch.empty():
        reminders_module.apply_batch(ln, batch)
    return values
