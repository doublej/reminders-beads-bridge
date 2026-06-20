"""Settings list: one reminder per control. Three kinds:

- ``toggle`` — completed = enabled (e.g. show_completed).
- ``action`` — completing it fires a one-shot action; sync auto-resets it to
  unchecked and reports ``True`` for that cycle (e.g. restart the bridge).
- ``value`` — an integer the user edits inside the ``<rb:value>`` tag in the
  body; sync parses + clamps it and re-renders the body (e.g. poll interval).

Every setting body ends with exactly one daemon-owned control tag — the strong,
repeatable grammar the surface is parsed against:

    <rb:toggle/>                              # toggle: state lives in the checkbox
    <rb:action/>                              # action: fire via the checkbox
    <rb:value min="100" max="600000">5000</rb:value>   # value: edit the number

The tag is re-rendered every sync, so a deleted/mangled tag self-heals and an
out-of-range value visibly snaps to the clamped one. Free prose above the tag is
the human description; only the tag is read back.

The list is bridge-global (restart, poll interval, display toggles), so it lives
under the bare `_rb_` namespace rather than the beads `_rb_beads_` prefix —
overridable via RBRIDGE_SETTINGS_LIST. Pre-rename names are migrated losslessly
by `migrate.py` (rename, not delete — preserves the user's configured values).
"""

import os
import re
from dataclasses import dataclass

from . import reminders as reminders_module

_LIST_NAME = os.getenv("RBRIDGE_SETTINGS_LIST", "_rb_settings")
_VALUE_RE = re.compile(r"<rb:value\b[^>]*>\s*(-?\d+)\s*</rb:value>")


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
        key="dashboard",
        title="Dashboard server",
        body=(
            "Check to run the read-only at-a-glance HTTP endpoint (managed by "
            "the bridge as a child process). When on, open the URL in the "
            "_rb_dashboard reminder for projects, bead counts, and recent "
            "activity in one fetch. Uncheck to stop it."
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
        key="poll_ms",
        title="Poll interval (ms)",
        kind="value",
        vdefault=5000,
        vmin=100,
        vmax=600000,
        body=(
            "How often the bridge polls when no Reminders change event has "
            "fired, in milliseconds (100–600000). Edit the number inside the "
            "<rb:value> tag below, then save. Lower = faster, heavier. Note: the bridge "
            "already syncs instantly on Reminders changes, so this mainly speeds "
            "up picking up non-Reminders changes (beads, tabs); the effective "
            "rate is bounded by how long a sync takes (~seconds)."
        ),
    ),
)


def list_name() -> str:
    return _LIST_NAME


def _clamp(s: Setting, v: int) -> int:
    return max(s.vmin, min(s.vmax, v))


def _control_tag(s: Setting, value: int) -> str:
    if s.kind == "value":
        return f'<rb:value min="{s.vmin}" max="{s.vmax}">{value}</rb:value>'
    if s.kind == "action":
        return "<rb:action/>"
    return "<rb:toggle/>"


def _rendered_body(s: Setting, value: int = 0) -> str:
    return f"{s.body}\n\n{_control_tag(s, value)}"


def _default(s: Setting) -> "bool | int":
    return s.vdefault if s.kind == "value" else s.default


def defaults() -> "dict[str, bool | int]":
    return {s.key: _default(s) for s in SETTINGS}


def _reconcile(s: Setting, keep: reminders_module.Reminder, batch) -> "bool | int":
    """Diff one existing reminder against its setting; return the resolved value."""
    if s.kind == "value":
        found = _VALUE_RE.findall(keep.body)
        value = _clamp(s, int(found[-1])) if found else s.vdefault
        expected = _rendered_body(s, value)
        if keep.body != expected:
            batch.updates.append({"id": keep.id, "body": expected})
        return value
    if s.kind == "action":
        fired = bool(keep.completed)
        patch: dict = {"id": keep.id}
        if keep.body != _rendered_body(s):
            patch["body"] = _rendered_body(s)
        if fired:
            patch["completed"] = False  # auto-reset one-shot
        if len(patch) > 1:
            batch.updates.append(patch)
        return fired
    if keep.body != _rendered_body(s):
        batch.updates.append({"id": keep.id, "body": _rendered_body(s)})
    return bool(keep.completed)


def _create_body(s: Setting) -> str:
    return _rendered_body(s, s.vdefault)


def sync() -> "dict[str, bool | int]":
    """Reconcile settings list. Return {key: value} for every known setting."""
    ln = list_name()
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
