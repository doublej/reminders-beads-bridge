"""Settings list: one reminder per control. Three kinds:

- ``toggle`` — completed = enabled (e.g. show_completed).
- ``action`` — completing it fires a one-shot action; sync auto-resets it to
  unchecked and reports ``True`` for that cycle (e.g. restart the bridge).
- ``value`` — an integer the user edits on the ``value:`` line in the body;
  sync parses + clamps it and re-renders the body (e.g. poll interval).

The list is bridge-global (restart, poll interval, display toggles), so it lives
under the `rbridge:` namespace rather than the beads `{prefix}` — overridable via
RBRIDGE_SETTINGS_LIST. The pre-rename `{prefix}Settings` list is deleted on sync.
"""

import os
import re
from dataclasses import dataclass

from . import reminders as reminders_module

_LIST_NAME = os.getenv("RBRIDGE_SETTINGS_LIST", "rbridge: Settings")
_VALUE_RE = re.compile(r"(?mi)^[ \t]*value:[ \t]*(\d+)")


@dataclass(frozen=True)
class Setting:
    key: str
    title: str
    body: str
    kind: str = "toggle"  # toggle | action | value
    default: bool = False
    vdefault: int = 0
    vmin: int = 0
    vmax: int = 0


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
    Setting(
        key="restart",
        title="Restart bridge",
        kind="action",
        body=(
            "Complete this reminder to restart the bridge daemon (reloads code "
            "and re-reads settings). It un-completes itself once the restart "
            "begins — no need to uncheck it."
        ),
    ),
    Setting(
        key="poll_interval",
        title="Poll interval (seconds)",
        kind="value",
        vdefault=5,
        vmin=1,
        vmax=600,
        body=(
            "How often the bridge polls when no Reminders change event has "
            "fired (1–600). Edit the number on the value line below, then save. "
            "Lower = more responsive, higher = lighter."
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


def _clamp(s: Setting, v: int) -> int:
    return max(s.vmin, min(s.vmax, v))


def _value_body(s: Setting, value: int) -> str:
    return f"{s.body}\n\nvalue: {value}"


def _default(s: Setting) -> "bool | int":
    return s.vdefault if s.kind == "value" else s.default


def defaults() -> "dict[str, bool | int]":
    return {s.key: _default(s) for s in SETTINGS}


def _reconcile(s: Setting, keep: reminders_module.Reminder, batch) -> "bool | int":
    """Diff one existing reminder against its setting; return the resolved value."""
    if s.kind == "value":
        found = _VALUE_RE.findall(keep.body)
        value = _clamp(s, int(found[-1])) if found else s.vdefault
        expected = _value_body(s, value)
        if keep.body != expected:
            batch.updates.append({"id": keep.id, "body": expected})
        return value
    if s.kind == "action":
        fired = bool(keep.completed)
        patch: dict = {"id": keep.id}
        if keep.body != s.body:
            patch["body"] = s.body
        if fired:
            patch["completed"] = False  # auto-reset one-shot
        if len(patch) > 1:
            batch.updates.append(patch)
        return fired
    if keep.body != s.body:
        batch.updates.append({"id": keep.id, "body": s.body})
    return bool(keep.completed)


def _create_body(s: Setting) -> str:
    return _value_body(s, s.vdefault) if s.kind == "value" else s.body


def sync(prefix: str) -> "dict[str, bool | int]":
    """Reconcile settings list. Return {key: value} for every known setting."""
    ln = list_name()
    _delete_legacy(prefix)
    reminders_module.create_list(ln)
    by_name: dict[str, list[reminders_module.Reminder]] = {}
    for r in reminders_module.list_reminders(ln):
        by_name.setdefault(r.name, []).append(r)

    values = defaults()
    expected = {s.title for s in SETTINGS}
    batch = reminders_module.Batch()

    for s in SETTINGS:
        matches = by_name.get(s.title, [])
        if not matches:
            batch.creates.append({"name": s.title, "body": _create_body(s), "priority": 0})
            continue
        for extra in matches[1:]:
            batch.deletes.append(extra.id)
        values[s.key] = _reconcile(s, matches[0], batch)

    for name, matches in by_name.items():
        if name not in expected:
            for r in matches:
                batch.deletes.append(r.id)

    if not batch.empty():
        reminders_module.apply_batch(ln, batch)
    return values
