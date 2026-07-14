"""Per-lane last-success / last-error heartbeat, so a silently-broken lane shows.

A lane that stops succeeding (e.g. the 2-week bd-PATH reconcile outage) leaves no
error anyone reads. This records last-ok/last-err per lane and persists it for
cross-process readers (doctor). Surfaced in `_rb_dashboard` and `doctor` — making
breakage visible-in-store, per CLAUDE.md → Design stance.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_PATH = Path("~/.claude/reminders-bridge-heartbeat.json").expanduser()
_state: dict[str, dict] = {}


def ok(lane: str) -> None:
    e = _state.setdefault(lane, {})
    e["ok_at"] = time.time()
    e.pop("err", None)
    e.pop("err_at", None)


def fail(lane: str, msg: str) -> None:
    e = _state.setdefault(lane, {})
    e["err_at"] = time.time()
    e["err"] = msg[:200]


def persist() -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(_state, indent=2))
        tmp.replace(_PATH)
    except OSError:
        pass


def load() -> dict[str, dict]:
    try:
        return json.loads(_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _ago(s: float) -> str:
    if s < 90:
        return f"{int(s)}s"
    if s < 5400:
        return f"{int(s // 60)}m"
    if s < 172800:
        return f"{int(s // 3600)}h"
    return f"{int(s // 86400)}d"


def stale(data: dict[str, dict] | None = None, max_age_s: float = 900.0) -> list[str]:
    """Human-readable lines for lanes that are erroring or long overdue."""
    data = _state if data is None else data
    now = time.time()
    out = []
    for lane, e in sorted(data.items()):
        if e.get("err"):
            out.append(f"{lane}: erroring — {e['err']}")
            continue
        ok_at = e.get("ok_at")
        if ok_at is None:
            out.append(f"{lane}: never succeeded")
        elif now - ok_at > max_age_s:
            out.append(f"{lane}: last ok {_ago(now - ok_at)} ago")
    return out
