"""Standalone session triggers. No coupling to beads.

Two reminders lists, `Claude: Sessions` and `Codex: Sessions`. Each unchecked
reminder is a pending request: title is the prompt, optional `cwd: <path>`
line in the body sets the working directory, the rest of the body is appended
to the prompt. Daemon scans both lists every cycle, launches Ghostty for each
pending request, and marks the reminder completed.
"""

import logging
import os
import re
from pathlib import Path

from . import activity as activity_module
from . import launch as launch_module
from . import reminders as reminders_module

log = logging.getLogger(__name__)

_CWD_RE = re.compile(r"^[ \t]*cwd:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


def claude_list_name() -> str:
    return os.getenv("BBRIDGE_CLAUDE_LIST", "Claude: Sessions")


def codex_list_name() -> str:
    return os.getenv("BBRIDGE_CODEX_LIST", "Codex: Sessions")


def parse_request(rem: reminders_module.Reminder) -> tuple[Path, str]:
    cwd_match = _CWD_RE.search(rem.body)
    cwd = (
        Path(cwd_match.group(1)).expanduser()
        if cwd_match
        else Path.home()
    )
    body_extra = _CWD_RE.sub("", rem.body).strip()
    parts = [rem.name.strip()]
    if body_extra:
        parts += ["", body_extra]
    return cwd, "\n".join(parts)


def _process_list(list_name: str, cmd: str) -> int:
    reminders_module.create_list(list_name)
    pending = [r for r in reminders_module.list_reminders(list_name) if not r.completed]
    if not pending:
        return 0
    batch = reminders_module.Batch()
    launched = 0
    for rem in pending:
        cwd, prompt = parse_request(rem)
        try:
            launch_module.launch(cwd, prompt, cmd=cmd)
        except RuntimeError as e:
            log.warning("%s launch failed for %r: %s", cmd, rem.name, e)
            activity_module.record(list_name, f"{cmd}-error", "", str(e))
            continue
        log.info("Launched %s for %r in %s", cmd, rem.name, cwd)
        activity_module.record(list_name, f"{cmd}-launched", "", rem.name)
        batch.updates.append({"id": rem.id, "completed": True})
        launched += 1
    if not batch.empty():
        reminders_module.apply_batch(list_name, batch)
    return launched


def process_all() -> int:
    return _process_list(claude_list_name(), "claude") + _process_list(
        codex_list_name(), "codex"
    )
