"""Command queue: one reminder per action, executed and acked in place.

Generalizes the nav lane (navigation.py) so the voice agent gets ack/nack for
fire-and-forget actions without overloading the checkbox (CLAUDE.md → Design
stance). A reminder in `_rb_commands` titled `close:`/`reopen:`/`note:` names a
bead by id; the daemon acts on that bead's reminder and rewrites the command's
title in place to `ok:`/`error:` — the rewrite is the loop guard, exactly like
`fetch:`→`file:`. No state file: a crash mid-run just re-runs deterministically.

Grammar:
  close: <bead-id>            → complete the bead's reminder (daemon then bd-closes)
  reopen: <bead-id>           → uncomplete it
  note: <bead-id> | <text>    → append <text> to that bead's <bb:notes> (safe RMW)
"""

from __future__ import annotations

import os
import re

from . import activity as activity_module
from . import body as body_module
from . import link as link_module
from . import projects as projects_module
from . import reminders as reminders_module

_LIST = os.getenv("RBRIDGE_COMMANDS_LIST", "_rb_commands")
_VERB_RE = re.compile(
    r"^(?P<verb>close|reopen|note)\s*:\s*(?P<arg>.*)$", re.IGNORECASE | re.DOTALL
)
_HEADER = "How this list works"
_HEADER_BODY = (
    "Add a reminder to queue an action; the daemon runs it and rewrites the "
    "title to ok:/error: within ~5s (leave it unchecked).\n\n"
    "  close: <bead-id>\n"
    "  reopen: <bead-id>\n"
    "  note: <bead-id> | <text>   (appended to the bead's notes)\n\n"
    "Daemon-owned header — do not edit or complete."
)


def list_name() -> str:
    return _LIST


def sync(projects: list[projects_module.Project]) -> None:
    """Execute pending command reminders against the visible projects' beads."""
    reminders_module.create_list(_LIST)
    remote = reminders_module.list_reminders(_LIST)
    cmd_batch = reminders_module.Batch()
    _ensure_header(remote, cmd_batch)
    pending = [
        r for r in remote if not r.completed and _VERB_RE.match(r.name.strip())
    ]
    if pending:
        index = _index_beads(projects)
        targets: dict[str, reminders_module.Batch] = {}
        for cmd in pending:
            ack = _dispatch(cmd, index, targets)
            cmd_batch.updates.append({"id": cmd.id, "name": ack})
            activity_module.record(_LIST, "command", "", f"{cmd.name.strip()} → {ack}")
        for ln, b in targets.items():  # act on beads first, then ack
            reminders_module.apply_batch(ln, b)
    if not cmd_batch.empty():
        reminders_module.apply_batch(_LIST, cmd_batch)


def _ensure_header(remote, batch: reminders_module.Batch) -> None:
    matches = [r for r in remote if r.name == _HEADER]
    if not matches:
        batch.creates.append({"name": _HEADER, "body": _HEADER_BODY, "priority": 0})
    elif matches[0].body != _HEADER_BODY:
        batch.updates.append({"id": matches[0].id, "body": _HEADER_BODY})


def _index_beads(
    projects: list[projects_module.Project],
) -> dict[str, tuple[str, reminders_module.Reminder]]:
    """bead-id → (list_name, its reminder), across visible project lists."""
    index: dict[str, tuple[str, reminders_module.Reminder]] = {}
    for p in projects:
        by_id = link_module.index_by_bead_id(reminders_module.list_reminders(p.list_name))
        for bead_id, matches in by_id.items():
            index.setdefault(bead_id, (p.list_name, matches[0]))
    return index


def _dispatch(cmd, index, targets: dict[str, reminders_module.Batch]) -> str:
    m = _VERB_RE.match(cmd.name.strip())
    if m is None:  # unreachable — caller filters by the same regex
        return "error: unrecognized command"
    verb, arg = m.group("verb").lower(), m.group("arg").strip()

    if verb == "note":
        bead_id, sep, text = arg.partition("|")
        bead_id, text = bead_id.strip(), text.strip()
        if not sep or not text:
            return "error: use `note: <bead-id> | text`"
        hit = index.get(bead_id)
        if hit is None:
            return f"error: {bead_id} not found"
        ln, r = hit
        new_body = body_module.append_note(r.body, text)
        if new_body is None:
            return f"error: {bead_id} has no notes block yet"
        targets.setdefault(ln, reminders_module.Batch()).updates.append(
            {"id": r.id, "body": new_body}
        )
        return f"ok: noted on {bead_id}"

    bead_id = arg.strip()
    hit = index.get(bead_id)
    if hit is None:
        return f"error: {bead_id} not found"
    ln, r = hit
    completed = verb == "close"
    targets.setdefault(ln, reminders_module.Batch()).updates.append(
        {"id": r.id, "completed": completed}
    )
    return f"ok: {bead_id} {'marked done' if completed else 'reopened'}"
