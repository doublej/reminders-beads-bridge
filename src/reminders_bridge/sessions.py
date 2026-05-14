"""Multi-turn chat-mode sessions driven from the reminder body.

A reminder in `Claude: Sessions` with `chat: true` becomes a persistent
conversation: any `you:` block at the end (no `claude:` block after it)
triggers a non-interactive `claude -p` turn. Daemon appends the response,
leaves the reminder unchecked for more turns. Check to close, uncheck +
add a new `you:` block to reopen and continue. Session id from the first
turn is written to a `session:` header and reused via `--resume`.
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import activity as activity_module
from . import launch as launch_module
from . import reminders as reminders_module

log = logging.getLogger(__name__)

_STATE_PATH = Path(
    os.getenv(
        "RBRIDGE_SESSIONS_STATE",
        str(Path.home() / ".claude/reminders-bridge-sessions.json"),
    )
)
_TIMEOUT_S = int(os.getenv("RBRIDGE_SESSIONS_TIMEOUT_S", "900"))
_HEADER_KEYS = ("cwd", "chat", "session")
_HEADER_RE = re.compile(
    rf"^[ \t]*({'|'.join(_HEADER_KEYS)}):[ \t]*(.*?)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_YOU_RE = re.compile(r"^[ \t]*you:[ \t]*", re.MULTILINE | re.IGNORECASE)
_CLAUDE_RE = re.compile(
    r"^[ \t]*claude(?:[ \t]*\([^)]*\))?:[ \t]*", re.MULTILINE | re.IGNORECASE
)


@dataclass
class Turn:
    reminder_id: str
    list_name: str
    pid: int
    stdout_path: str
    started_at: float


def _load() -> list[Turn]:
    if not _STATE_PATH.exists():
        return []
    try:
        data = json.loads(_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [Turn(**t) for t in data.get("turns", [])]


def _save(turns: list[Turn]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps({"turns": [asdict(t) for t in turns]}, indent=2))


def active_reminder_ids() -> set[str]:
    return {t.reminder_id for t in _load()}


def _headers(body: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _HEADER_RE.finditer(body)}


def is_chat(body: str) -> bool:
    return _headers(body).get("chat", "").lower() in {"true", "yes", "1"}


def _transcript(body: str) -> str:
    return _HEADER_RE.sub("", body).strip()


def pending_user_text(body: str, title: str) -> str | None:
    transcript = _transcript(body)
    you_matches = list(_YOU_RE.finditer(transcript))
    claude_matches = list(_CLAUDE_RE.finditer(transcript))
    if you_matches:
        last_you = you_matches[-1]
        last_claude_pos = claude_matches[-1].start() if claude_matches else -1
        if last_you.start() < last_claude_pos:
            return None
        text = transcript[last_you.end():].strip()
        return text or None
    if transcript and not claude_matches:
        return transcript
    if not transcript and title.strip():
        return title.strip()
    return None


def _compose(body: str, response: str, session_id: str) -> str:
    h = _headers(body)
    h["chat"] = "true"
    if session_id:
        h["session"] = session_id
    transcript = _transcript(body).rstrip()
    if not _YOU_RE.search(transcript) and transcript:
        transcript = f"you:\n{transcript}"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header_block = "\n".join(f"{k}: {h[k]}" for k in _HEADER_KEYS if k in h)
    return f"{header_block}\n\n{transcript}\n\nclaude ({ts}):\n{response.rstrip()}\n"


def _launch_turn(rem_id: str, list_name: str, prompt: str, cwd: Path, sid: str | None) -> None:
    out = f"/tmp/rbridge-session-{rem_id.replace('/', '_')}-{int(time.time())}.out"
    argv = [launch_module.session_bin("claude"), "-p", "--output-format", "json"]
    if sid:
        argv += ["--resume", sid]
    extra = os.getenv("RBRIDGE_CLAUDE_FLAGS", "").split()
    argv += extra + [prompt]
    with open(out, "w") as fh:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT, start_new_session=True
        )
    _save(_load() + [Turn(rem_id, list_name, proc.pid, out, time.time())])
    log.info("session turn launched: pid=%s reminder=%s resume=%s", proc.pid, rem_id, bool(sid))


def _extract_result(raw: str) -> tuple[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or "(no response)", ""
    events = data if isinstance(data, list) else [data]
    result_event = next(
        (e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result"),
        events[-1] if events else {},
    )
    response = (result_event.get("result") or "").strip() or "(no response)"
    return response, result_event.get("session_id") or ""


def _pid_alive(pid: int) -> bool:
    try:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False
    except (ChildProcessError, OSError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _finalize(t: Turn) -> bool:
    p = Path(t.stdout_path)
    raw = p.read_text(errors="replace") if p.exists() else ""
    response, new_sid = _extract_result(raw)
    rem = next(
        (r for r in reminders_module.list_reminders(t.list_name) if r.id == t.reminder_id),
        None,
    )
    if rem is None:
        p.unlink(missing_ok=True)
        return True
    sid = new_sid or _headers(rem.body).get("session", "")
    new_body = _compose(rem.body, response, sid)
    batch = reminders_module.Batch()
    batch.updates.append({"id": t.reminder_id, "body": new_body, "completed": False})
    try:
        reminders_module.apply_batch(t.list_name, batch)
    except RuntimeError as e:
        log.warning("session finalize failed for %s: %s", t.reminder_id, e)
        return False
    activity_module.record(t.list_name, "claude-turn", "", f"pid={t.pid} sid={sid[:8]}")
    log.info("session turn finalized: pid=%s sid=%s", t.pid, sid[:8])
    p.unlink(missing_ok=True)
    return True


def poll() -> None:
    list_name = os.getenv("RBRIDGE_CLAUDE_LIST", "Claude: Sessions")
    in_flight = _load()
    keep: list[Turn] = []
    now = time.time()
    for t in in_flight:
        alive = _pid_alive(t.pid)
        if alive and (now - t.started_at) < _TIMEOUT_S:
            keep.append(t)
            continue
        if alive:
            try:
                os.killpg(os.getpgid(t.pid), 15)
            except (OSError, ProcessLookupError):
                pass
        if not _finalize(t):
            keep.append(t)
    if len(keep) != len(in_flight):
        _save(keep)
    active = {t.reminder_id for t in keep}
    for rem in reminders_module.list_reminders(list_name):
        if rem.completed or rem.id in active or not is_chat(rem.body):
            continue
        prompt = pending_user_text(rem.body, rem.name)
        if not prompt:
            continue
        h = _headers(rem.body)
        cwd = Path(h.get("cwd", "~")).expanduser()
        if not cwd.exists():
            cwd = Path.home()
        sid = h.get("session") or None
        try:
            _launch_turn(rem.id, list_name, prompt, cwd, sid)
        except OSError as e:
            log.warning("session launch failed for %s: %s", rem.id, e)
            activity_module.record(list_name, "claude-error", "", str(e))
