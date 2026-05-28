"""Background capture for trigger sessions.

When a Claude/Codex Sessions reminder body has `capture: true`, the daemon
launches the prompt in print-mode (`claude -p` / `codex exec`), captures
stdout to a tempfile, and on exit writes the result back to the reminder
body and marks it completed. Reminder stays unchecked until output lands.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import activity as activity_module
from . import atomicio as atomicio_module
from . import launch as launch_module
from . import reminders as reminders_module

log = logging.getLogger(__name__)

_STATE_PATH = Path(
    os.getenv(
        "RBRIDGE_CAPTURE_STATE",
        str(Path.home() / ".claude/reminders-bridge-captures.json"),
    )
)
_TIMEOUT_S = int(os.getenv("RBRIDGE_CAPTURE_TIMEOUT_S", "1800"))


@dataclass
class Capture:
    reminder_id: str
    list_name: str
    cmd: str
    pid: int
    stdout_path: str
    started_at: float


def _load() -> list[Capture]:
    if not _STATE_PATH.exists():
        return []
    try:
        data = json.loads(_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [Capture(**c) for c in data.get("captures", [])]


def _save(captures: list[Capture]) -> None:
    atomicio_module.atomic_write_text(
        _STATE_PATH, json.dumps({"captures": [asdict(c) for c in captures]}, indent=2)
    )


def active_reminder_ids() -> set[str]:
    return {c.reminder_id for c in _load()}


def _build_argv(cmd: str, prompt: str) -> list[str]:
    bin_ = launch_module.session_bin(cmd)
    if cmd == "claude":
        return [bin_, "-p", prompt]
    if cmd == "codex":
        return [bin_, "exec", prompt]
    return [bin_, prompt]


def launch_capture(
    reminder_id: str, list_name: str, cmd: str, prompt: str, cwd: Path
) -> None:
    out_path = f"/tmp/rbridge-capture-{reminder_id.replace('/', '_')}.out"
    fh = open(out_path, "w")
    try:
        proc = subprocess.Popen(
            _build_argv(cmd, prompt),
            cwd=str(cwd),
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        fh.close()
    captures = _load()
    captures.append(
        Capture(
            reminder_id=reminder_id,
            list_name=list_name,
            cmd=cmd,
            pid=proc.pid,
            stdout_path=out_path,
            started_at=time.time(),
        )
    )
    _save(captures)
    log.info(
        "capture launched: %s pid=%s reminder=%s out=%s",
        cmd,
        proc.pid,
        reminder_id,
        out_path,
    )


def _pid_alive(pid: int) -> bool:
    try:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _finalize(c: Capture) -> bool:
    try:
        output = Path(c.stdout_path).read_text(errors="replace")
    except OSError:
        output = "(could not read capture output)"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snippet = output.strip() or "(no output)"
    rem_list = reminders_module.list_reminders(c.list_name)
    rem = next((r for r in rem_list if r.id == c.reminder_id), None)
    if rem is None:
        log.warning("capture finalize: reminder %s gone", c.reminder_id)
        try:
            Path(c.stdout_path).unlink()
        except OSError:
            pass
        return True
    new_body = (
        rem.body.rstrip()
        + f"\n\n--- {c.cmd} output {ts} ---\n{snippet}\n"
    ).strip()
    batch = reminders_module.Batch()
    batch.updates.append(
        {"id": c.reminder_id, "body": new_body, "completed": True}
    )
    try:
        reminders_module.apply_batch(c.list_name, batch)
    except RuntimeError as e:
        log.warning("capture finalize failed for %s: %s", c.reminder_id, e)
        return False
    activity_module.record(
        c.list_name, f"{c.cmd}-captured", "", f"pid={c.pid} chars={len(snippet)}"
    )
    log.info(
        "capture finalized: %s pid=%s chars=%d", c.cmd, c.pid, len(snippet)
    )
    try:
        Path(c.stdout_path).unlink()
    except OSError:
        pass
    return True


def poll() -> None:
    captures = _load()
    if not captures:
        return
    keep: list[Capture] = []
    changed = False
    now = time.time()
    for c in captures:
        alive = _pid_alive(c.pid)
        timed_out = (now - c.started_at) >= _TIMEOUT_S
        if alive and not timed_out:
            keep.append(c)
            continue
        if timed_out and alive:
            try:
                os.killpg(os.getpgid(c.pid), 15)
            except (OSError, ProcessLookupError):
                pass
            activity_module.record(
                c.list_name, f"{c.cmd}-timeout", "", f"pid={c.pid}"
            )
        if _finalize(c):
            changed = True
        else:
            keep.append(c)
    if changed or len(keep) != len(captures):
        _save(keep)
