"""Rolling activity log surfaced as a single reminder."""

import datetime as _dt
import json
import os
from collections import deque
from pathlib import Path
from typing import Deque

from . import reminders as reminders_module

_LIST_SUFFIX = "Activity"
_LEGACY_SUFFIXES = ("__log__",)
_TITLE = "Recent activity"
_MAX_ENTRIES = 200
_DEFAULT_PATH = Path("~/.claude/reminders-bridge-activity.jsonl").expanduser()


def _path() -> Path:
    return Path(os.getenv("RBRIDGE_ACTIVITY", str(_DEFAULT_PATH))).expanduser()


def list_name(prefix: str) -> str:
    return f"{prefix}{_LIST_SUFFIX}"


def record(project: str, kind: str, bead_id: str | None = None, detail: str = "") -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project": project,
        "kind": kind,
        "bead_id": bead_id or "",
        "detail": detail,
    }
    with p.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _tail() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    buf: Deque[str] = deque(maxlen=_MAX_ENTRIES)
    with p.open() as f:
        for line in f:
            line = line.rstrip()
            if line:
                buf.append(line)
    out: list[dict] = []
    for line in buf:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _format(entries: list[dict]) -> str:
    if not entries:
        return "(no activity yet)"
    lines = []
    for e in reversed(entries):
        bead = e["bead_id"] or "-"
        lines.append(
            f"{e['ts']}  {e['project']:<20.20} {e['kind']:<10.10} {bead:<10.10} {e['detail']}"
        )
    return "\n".join(lines)


def sync(prefix: str) -> None:
    ln = list_name(prefix)
    for legacy in _LEGACY_SUFFIXES:
        try:
            reminders_module.delete_list(f"{prefix}{legacy}")
        except RuntimeError:
            pass
    reminders_module.create_list(ln)
    remote = reminders_module.list_reminders(ln)
    body = _format(_tail())
    matches = [r for r in remote if r.name == _TITLE]
    extras = [r for r in remote if r.name != _TITLE]
    batch = reminders_module.Batch()
    if not matches:
        batch.creates.append({"name": _TITLE, "body": body, "priority": 0})
    else:
        keep = matches[0]
        if keep.body != body:
            batch.updates.append({"id": keep.id, "body": body})
        for dup in matches[1:]:
            batch.deletes.append(dup.id)
    for extra in extras:
        batch.deletes.append(extra.id)
    if not batch.empty():
        reminders_module.apply_batch(ln, batch)


def prune(max_bytes: int = 2_000_000) -> None:
    p = _path()
    if not p.exists() or p.stat().st_size <= max_bytes:
        return
    entries = _tail()
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
