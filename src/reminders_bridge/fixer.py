"""Fixer escalation: hand a chat session the daemon's state + arch context.

A chat-mode reminder marked `fixer: true` gets a base prompt prepended on
its first turn — recent daemon log, captures/sessions state, project
paths, and architecture rules — so the spawned `claude -p` knows what
it's looking at without the user having to spell it out. Subsequent
turns reuse the session id and don't need the wrapper.

Also exposed: `trigger_auto(errors)`, called from `daemon._safe` after
N consecutive failures, which creates a new fixer reminder in
`Claude: Sessions` for self-repair. Cooldown prevents loops.
"""

import logging
import os
import re
import time
from pathlib import Path

from . import reminders as reminders_module

log = logging.getLogger(__name__)

_FIXER_RE = re.compile(
    r"^[ \t]*fixer:[ \t]*(true|yes|1)[ \t]*$", re.MULTILINE | re.IGNORECASE
)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOG_PATH = Path.home() / "Library/Logs/reminders-bridge.log"
_CAPTURES_STATE = Path.home() / ".claude/reminders-bridge-captures.json"
_SESSIONS_STATE = Path.home() / ".claude/reminders-bridge-sessions.json"
_COOLDOWN_FILE = Path.home() / ".claude/reminders-bridge-fixer-cooldown"
_TAIL_LINES = int(os.getenv("RBRIDGE_FIXER_LOG_LINES", "120"))
_COOLDOWN_S = int(os.getenv("RBRIDGE_FIXER_COOLDOWN_S", "3600"))


def is_fixer(body: str) -> bool:
    return bool(_FIXER_RE.search(body))


def wrap_prompt(user_prompt: str) -> str:
    return (
        "You are the rbridge fixer agent. The reminders-bridge daemon "
        "(Apple Reminders <-> Beads sync + Claude/Codex session triggers + "
        "chat-mode multi-turn sessions) needs investigation or repair. "
        "Recent log, runtime state, and project paths are below.\n\n"
        f"Project root: {_PROJECT_ROOT}\n"
        f"Daemon log:   {_LOG_PATH}\n"
        f"launchd:      ~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist\n"
        f"Arch rules:   {_PROJECT_ROOT / 'CLAUDE.md'} (read before editing code)\n\n"
        "=== Daemon log tail ===\n"
        f"{_tail(_LOG_PATH)}\n"
        "=== Captures state ===\n"
        f"{_read(_CAPTURES_STATE)}\n"
        "=== Sessions state ===\n"
        f"{_read(_SESSIONS_STATE)}\n"
        "=== Constraints ===\n"
        "- Keep modules under ~150 lines. Single responsibility per module.\n"
        "- Reload after edits: launchctl unload+load the plist.\n"
        "- Commit your fix on the current branch; do not push.\n"
        "- If you cannot reproduce, say so — do not invent a fix.\n\n"
        "=== User request ===\n"
        f"{user_prompt}"
    )


def trigger_auto(errors: list[str], list_name: str) -> bool:
    if _recently_escalated():
        return False
    body = (
        f"cwd: {_PROJECT_ROOT}\n"
        "chat: true\n"
        "fixer: true\n\n"
        "you:\n"
        "Auto-escalation: the rbridge daemon hit consecutive failures:\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\nFigure out the root cause and propose or apply a minimal fix.\n"
    )
    try:
        reminders_module.create_list(list_name)
        batch = reminders_module.Batch()
        batch.creates.append({"name": "rbridge auto-fixer", "body": body})
        reminders_module.apply_batch(list_name, batch)
    except RuntimeError as e:
        log.error("Fixer auto-escalation failed: %s", e)
        return False
    _mark_escalated()
    log.warning("Fixer auto-escalation: created reminder in %s", list_name)
    return True


def _tail(path: Path) -> str:
    if not path.exists():
        return "(missing)"
    try:
        with open(path) as f:
            return "".join(f.readlines()[-_TAIL_LINES:])
    except OSError as e:
        return f"(read failed: {e})"


def _read(path: Path) -> str:
    if not path.exists():
        return "(missing)"
    try:
        text = path.read_text()
        return text if len(text) < 8000 else text[:8000] + "\n…(truncated)\n"
    except OSError as e:
        return f"(read failed: {e})"


def _recently_escalated() -> bool:
    if not _COOLDOWN_FILE.exists():
        return False
    return (time.time() - _COOLDOWN_FILE.stat().st_mtime) < _COOLDOWN_S


def _mark_escalated() -> None:
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COOLDOWN_FILE.touch()
