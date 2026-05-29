"""`Claude: Tabs` lane — one reminder per live Ghostty tab running Claude Code.

Read side: each reminder body mirrors the tab's title, status, and a live tail
of its session transcript. Send side: type a message under `send:` and complete
the reminder; the daemon switches Ghostty to that tab and types the message in
(`inject.py`) — as you would. On failure the message is kept for retry.

Reminders are keyed by pid and GC'd when the tab exits — this lane reflects live
tabs, it is not a persistent chat store.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import activity as activity_module
from . import atomicio as atomicio_module
from . import ghostty as ghostty_module
from . import inject as inject_module
from . import reminders as reminders_module
from . import tabsbody as tabsbody_module
from . import transcript as transcript_module

log = logging.getLogger(__name__)

_STATE_PATH = Path(
    os.getenv("RBRIDGE_TABS_STATE", str(Path.home() / ".claude/reminders-bridge-tabs.json"))
)


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
    return tabs.setdefault(key, {"reminder_id": "", "turns": [], "last_error": ""})


def _try_send(ent: dict, session, payload: str) -> None:
    """Type the payload into the tab. Success clears the carry; failure keeps it."""
    title = session.title if session else ""
    try:
        inject_module.type_into_tab(title, payload)
    except inject_module.InjectError as e:
        ent["last_error"] = str(e)
        activity_module.record(list_name(), "tab-send-failed", "", str(e))
        return
    ent["turns"].append({"role": "you", "ts": _now(), "text": payload})
    ent["last_error"] = ""
    activity_module.record(list_name(), "tab-send", "", f"chars={len(payload)}")


def _sync_tab(tab, state: dict, by_id: dict, batch, new_keys: list[str]) -> None:
    key = str(tab.pid)
    ent = _entry(state, key)
    session = transcript_module.resolve(tab.pid, tab.cwd)
    rem = by_id.get(ent["reminder_id"])
    carry = tabsbody_module.parse_send(rem.body) if rem else ""
    if rem and rem.completed and carry:
        _try_send(ent, session, carry)
        carry = carry if ent["last_error"] else ""
    body = tabsbody_module.compose(tab, session, ent["turns"], carry, ent.get("last_error", ""))
    title = tabsbody_module.title(tab, session)
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
    reminders_module.create_list(ln)
    by_id = {r.id: r for r in reminders_module.list_reminders(ln)}
    batch = reminders_module.Batch()
    new_keys: list[str] = []
    live = {str(t.pid) for t in tabs_disc}

    for tab in tabs_disc:
        _sync_tab(tab, state, by_id, batch, new_keys)
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
