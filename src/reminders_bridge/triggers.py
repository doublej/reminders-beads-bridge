"""Standalone session triggers. No coupling to beads.

Two reminders lists, `_rb_claude_sessions` and `_rb_codex_sessions`. Each unchecked
reminder is a pending request: title is the prompt, optional `cwd: <path>`
line in the body sets the working directory, the rest of the body is appended
to the prompt. Daemon scans both lists every cycle and launches a headless
`capture: true` run for each pending request.

The interactive path (spawn the prompt in a new terminal window) was Ghostty-only
and is gone; a pending reminder with neither `capture:` nor `chat:` is left
untouched for the user to fix rather than retried forever.
"""

import logging
import os
import re
from pathlib import Path

from . import activity as activity_module
from . import captures as captures_module
from . import reminders as reminders_module
from . import sessions as sessions_module

log = logging.getLogger(__name__)

_CWD_RE = re.compile(r"^[ \t]*cwd:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_CAPTURE_RE = re.compile(
    r"^[ \t]*capture:[ \t]*(true|yes|1)[ \t]*$", re.MULTILINE | re.IGNORECASE
)


def claude_list_name() -> str:
    return os.getenv("RBRIDGE_CLAUDE_LIST", "_rb_claude_sessions")


def codex_list_name() -> str:
    return os.getenv("RBRIDGE_CODEX_LIST", "_rb_codex_sessions")


def parse_request(rem: reminders_module.Reminder) -> tuple[Path, str, bool]:
    cwd_match = _CWD_RE.search(rem.body)
    cwd = (
        Path(cwd_match.group(1)).expanduser()
        if cwd_match
        else Path.home()
    )
    capture = bool(_CAPTURE_RE.search(rem.body))
    stripped = _CAPTURE_RE.sub("", _CWD_RE.sub("", rem.body)).strip()
    parts = [rem.name.strip()]
    if stripped:
        parts += ["", stripped]
    return cwd, "\n".join(parts), capture


def _process_list(list_name: str, cmd: str) -> int:
    reminders_module.create_list(list_name)
    in_flight = captures_module.active_reminder_ids() | sessions_module.active_reminder_ids()
    pending = [
        r
        for r in reminders_module.list_reminders(list_name)
        if not r.completed and r.id not in in_flight and not sessions_module.is_chat(r.body)
    ]
    if not pending:
        return 0
    launched = 0
    for rem in pending:
        cwd, prompt, capture = parse_request(rem)
        if not capture:
            continue
        try:
            captures_module.launch_capture(rem.id, list_name, cmd, prompt, cwd)
        except OSError as e:
            log.warning("%s capture-launch failed for %r: %s", cmd, rem.name, e)
            activity_module.record(list_name, f"{cmd}-error", "", str(e))
            continue
        log.info("Capture-launched %s for %r in %s", cmd, rem.name, cwd)
        activity_module.record(list_name, f"{cmd}-capture-queued", "", rem.name)
        launched += 1
    return launched


def process_all() -> int:
    return _process_list(claude_list_name(), "claude") + _process_list(
        codex_list_name(), "codex"
    )
