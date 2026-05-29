"""`Claude: Tabs` lane — one reminder per live Ghostty tab running Claude Code.

Read side: each reminder body mirrors the tab's status and a live tail of its
session transcript. Send side: type a message under `send:` and complete the
reminder; the daemon forks a headless turn (`tabsend.py`) from the session and
posts the reply back. Reminders are keyed by pid and GC'd when the tab exits —
this lane reflects live tabs, it is not a persistent chat store.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import activity as activity_module
from . import atomicio as atomicio_module
from . import ghostty as ghostty_module
from . import reminders as reminders_module
from . import tabsbody as tabsbody_module
from . import tabsend as tabsend_module
from . import transcript as transcript_module

log = logging.getLogger(__name__)

_STATE_PATH = Path(
    os.getenv("RBRIDGE_TABS_STATE", str(Path.home() / ".claude/reminders-bridge-tabs.json"))
)
_TAIL_MSGS = int(os.getenv("RBRIDGE_TABS_TAIL_MSGS", "6"))


def list_name() -> str:
    return os.getenv("RBRIDGE_TABS_LIST", "Claude: Tabs")


def _load() -> dict:
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text()).get("tabs", {})
    except (ValueError, OSError):
        return {}


def _save(tabs: dict) -> None:
    atomicio_module.atomic_write_text(_STATE_PATH, json.dumps({"tabs": tabs}, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry(tabs: dict, key: str) -> dict:
    return tabs.setdefault(key, {"reminder_id": "", "fork_sid": "", "turns": []})


def _dispatch(tab: ghostty_module.Tab, ent: dict, payload: str, sid: str) -> None:
    cwd = Path(tab.cwd) if tab.cwd and Path(tab.cwd).is_dir() else Path.home()
    resume = ent.get("fork_sid") or sid or None
    tabsend_module.launch(str(tab.pid), ent["reminder_id"], payload, cwd, resume)
    ent["turns"].append({"role": "you", "ts": _now(), "text": payload})
    activity_module.record(list_name(), "tab-send", "", f"pid={tab.pid} chars={len(payload)}")


def _apply_replies(tabs: dict) -> None:
    for res in tabsend_module.collect():
        ent = next((e for e in tabs.values() if e.get("reminder_id") == res.reminder_id), None)
        if ent is None:
            continue
        ent["turns"].append({"role": "claude", "ts": _now(), "text": res.response})
        if res.session_id:
            ent["fork_sid"] = res.session_id
        activity_module.record(list_name(), "tab-reply", "", f"chars={len(res.response)}")


def _sync_tab(tab: ghostty_module.Tab, state: dict, by_id: dict, busy: set[str], batch, new_keys: list[str]) -> None:
    key = str(tab.pid)
    ent = _entry(state, key)
    session = transcript_module.resolve_session(tab.cwd)
    sid = session.session_id if session else ""
    tail = transcript_module.render_tail(session.path, _TAIL_MSGS) if session else "(no session)"
    rem = by_id.get(ent["reminder_id"])
    if rem and rem.completed and key not in busy and tabsbody_module.parse_send(rem.body):
        _dispatch(tab, ent, tabsbody_module.parse_send(rem.body), sid)
        busy = busy | {key}
    body = tabsbody_module.compose(tab, sid, tail, ent["turns"], key in busy)
    title = tabsbody_module.title(tab)
    if rem is None:
        batch.creates.append({"name": title, "body": body, "priority": 1})
        new_keys.append(key)
        return
    patch: dict = {"id": rem.id}
    if rem.name != title:
        patch["name"] = title
    if rem.body != body:
        patch["body"] = body
    if rem.completed:
        patch["completed"] = False
    if len(patch) > 1:
        batch.updates.append(patch)


def sync() -> None:
    ln = list_name()
    tabs_disc = ghostty_module.discover()
    state = _load()
    if not tabs_disc and not state:
        return
    _apply_replies(state)
    reminders_module.create_list(ln)
    by_id = {r.id: r for r in reminders_module.list_reminders(ln)}
    busy = tabsend_module.active_keys()
    batch = reminders_module.Batch()
    new_keys: list[str] = []
    live = {str(t.pid) for t in tabs_disc}

    for tab in tabs_disc:
        _sync_tab(tab, state, by_id, busy, batch, new_keys)
    _gc(state, live, by_id, batch)

    new_ids = reminders_module.apply_batch(ln, batch) if not batch.empty() else []
    for key, rid in zip(new_keys, new_ids):
        state[key]["reminder_id"] = rid
        activity_module.record(ln, "tab-opened", "", f"pid={key}")
    _save(state)


def _gc(state: dict, live: set[str], by_id: dict, batch) -> None:
    for key in list(state):
        if key in live:
            continue
        rid = state[key].get("reminder_id")
        if rid and rid in by_id:
            batch.deletes.append(rid)
        activity_module.record(list_name(), "tab-closed", "", f"pid={key}")
        del state[key]
