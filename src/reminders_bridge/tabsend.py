"""Headless send-turns for the Claude: Tabs lane.

A "send" forks a `claude -p --output-format json --resume <sid>` continuation
from the tab's current session context, captures the reply, and reports it back
to `tabs.py`. Forking (and reusing the *returned* session id for follow-ups)
means we never write into the jsonl the live tab is actively appending to.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import atomicio as atomicio_module
from . import launch as launch_module
from . import procutil as procutil_module

log = logging.getLogger(__name__)

_STATE_PATH = Path(
    os.getenv(
        "RBRIDGE_TABS_TURNS_STATE",
        str(Path.home() / ".claude/reminders-bridge-tab-turns.json"),
    )
)
_TIMEOUT_S = int(os.getenv("RBRIDGE_TABS_TIMEOUT_S", "900"))


@dataclass
class Turn:
    key: str
    reminder_id: str
    pid: int
    stdout_path: str
    started_at: float


@dataclass
class Result:
    key: str
    reminder_id: str
    response: str
    session_id: str


def _load() -> list[Turn]:
    if not _STATE_PATH.exists():
        return []
    try:
        data = json.loads(_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [Turn(**t) for t in data.get("turns", [])]


def _save(turns: list[Turn]) -> None:
    atomicio_module.atomic_write_text(
        _STATE_PATH, json.dumps({"turns": [asdict(t) for t in turns]}, indent=2)
    )


def active_keys() -> set[str]:
    return {t.key for t in _load()}


def launch(key: str, reminder_id: str, prompt: str, cwd: Path, sid: str | None) -> None:
    out = f"/tmp/rbridge-tab-{key}-{int(time.time())}.out"
    argv = [launch_module.session_bin("claude"), "-p", "--output-format", "json"]
    if sid:
        argv += ["--resume", sid]
    argv += os.getenv("RBRIDGE_CLAUDE_FLAGS", "").split() + [prompt]
    with open(out, "w") as fh:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _save(_load() + [Turn(key, reminder_id, proc.pid, out, time.time())])
    log.info("tab turn launched: pid=%s key=%s resume=%s", proc.pid, key, bool(sid))


def _extract(raw: str) -> tuple[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or "(no response)", ""
    events = data if isinstance(data, list) else [data]
    result = next(
        (e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"),
        events[-1] if events else {},
    )
    response = (result.get("result") or "").strip() or "(no response)"
    return response, result.get("session_id") or ""


def collect() -> list[Result]:
    """Reap finished/timed-out turns, returning their replies."""
    turns = _load()
    if not turns:
        return []
    keep: list[Turn] = []
    results: list[Result] = []
    now = time.time()
    for t in turns:
        state = procutil_module.child_state(t.pid)
        timed_out = (now - t.started_at) >= _TIMEOUT_S
        if state == "running" and not timed_out:
            keep.append(t)
            continue
        if state == "running" and timed_out:
            try:
                os.killpg(os.getpgid(t.pid), 15)
            except (OSError, ProcessLookupError):
                pass
        p = Path(t.stdout_path)
        raw = p.read_text(errors="replace") if p.exists() else ""
        response, sid = _extract(raw)
        results.append(Result(t.key, t.reminder_id, response, sid))
        p.unlink(missing_ok=True)
    if len(keep) != len(turns):
        _save(keep)
    return results
