"""Title-prefix grammar and bead↔reminder field mappings."""

import re

from . import beads as beads_module
from . import reminders as reminders_module

_BD_TO_REM_PRIO = {0: 0, 1: 1, 2: 5, 3: 9, 4: 9}
_TITLE_PREFIX = re.compile(r"^([a-zA-Z0-9_.-]+):\s")


def bead_title(issue: beads_module.Issue) -> str:
    return f"{issue.id}: {issue.title}"


def bead_priority(issue: beads_module.Issue) -> int:
    return _BD_TO_REM_PRIO.get(issue.priority, 0)


def index_by_bead_id(
    reminders: list[reminders_module.Reminder],
) -> dict[str, list[reminders_module.Reminder]]:
    idx: dict[str, list[reminders_module.Reminder]] = {}
    for r in reminders:
        m = _TITLE_PREFIX.match(r.name)
        if not m:
            continue
        idx.setdefault(m.group(1), []).append(r)
    return idx
