"""`_rb_manager` lane — free text to the deckhand manager, reply written back in place.

The manager is the one Claude session inside the deckhand daemon that can read,
speak into, and start every Claude Code session on this Mac. Its wire is already
turn-based (`POST /manager/say` answers at once; `GET /manager?since=` is a file
with a cursor), so it fits the bridge's fire-and-forget model without any push.

Contract (the nav-lane pattern, `fetch:`→`file:`):
  new unchecked reminder      → posted; title becomes `sent: <text>` in the SAME
                                cycle and the body says what happens next — the
                                voice agent never has to wonder if it landed
  while the manager works     → every manager/act/note entry is appended to the
                                body as it arrives (partial progress is readable)
  when the run ends           → title becomes `reply: <first line>`
  daemon unreachable          → title untouched, body says so; retried next cycle

Entries between this message's `person` entry and the next one are its reply, so
several messages may be in flight — the manager queues them itself.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import activity as activity_module
from . import reminders as reminders_module

log = logging.getLogger(__name__)

_LIST = os.getenv("RBRIDGE_MANAGER_LIST", "_rb_manager")
_URL = os.getenv("RBRIDGE_DECKHAND_URL", "http://127.0.0.1:4180")
_TOKEN_PATH = Path.home() / "Library/Application Support/Deckhand/token"
_ACK_RE = re.compile(r"^(sent|reply|error)\s*:", re.IGNORECASE)
_TAG_RE = re.compile(r'<rb:manager entry="(?P<entry>\d+)" state="(?P<state>\w+)"/>')
_REPLY_HDR = "──── reply ────"
_HEADER = "How this list works"
_HEADER_BODY = (
    "Add a reminder whose title is a message to the deckhand manager — plain "
    "words, e.g. `tell quiet-margay to run the tests and report`, `what is every "
    "session doing`, `start a session in personal-homepage`. Leave it unchecked.\n\n"
    "Within ~5s the daemon rewrites the title to `sent:` and the body says what "
    "happens next. The manager's steps appear in the body as they happen; the "
    "title becomes `reply:` when it is done. Re-read the reminder next turn.\n\n"
    "Daemon-owned header — do not edit or complete."
)
# Daemon-side leverage: the first thing back is the plan, so the ack is never a spinner.
_PREAMBLE = (
    "Reply with ONE short line saying what you are about to do, then do it. "
    "Message: "
)


def list_name() -> str:
    return _LIST


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _call(path: str, payload: dict | None = None) -> dict:
    token = _TOKEN_PATH.read_text().strip()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        _URL + path, data=data, method="POST" if data else "GET",
        headers={"x-deckhand-token": token, "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _status_body(entry: int, state: str, status: str, reply_lines: list[str]) -> str:
    return "\n".join([
        f'<rb:manager entry="{entry}" state="{state}"/>',
        "──── status ────",
        status,
        "",
        _REPLY_HDR,
        *reply_lines,
    ]).rstrip() + "\n"


def _render(entries: list[dict]) -> list[str]:
    out = []
    for e in entries:
        stamp = datetime.fromtimestamp(e["said_at"], timezone.utc).strftime("%H:%M:%S")
        role = {"manager": "manager", "act": "  act", "note": "  note"}.get(e["role"], e["role"])
        out.append(f"{role} ({stamp}): {e['text']}")
    return out


def _send(rem: reminders_module.Reminder, batch: reminders_module.Batch) -> None:
    text = rem.name.strip()
    try:
        entry = _call("/manager/say", {"text": _PREAMBLE + text})["entry"]["id"]
    except (OSError, urllib.error.URLError, KeyError, ValueError) as e:
        batch.updates.append({"id": rem.id, "body": _status_body(
            0, "unsent",
            f"deckhand daemon not reachable at {_now()} ({e}). Message kept; "
            "the daemon retries every cycle — nothing to redo.", [],
        )})
        activity_module.record(_LIST, "manager-unreachable", "", str(e))
        return
    status = (
        f"Received {_now()} and handed to the deckhand manager (entry {entry}).\n"
        "Next: the manager states its plan on its first line, then acts. Each "
        "step is appended under the reply heading as it happens, and the title "
        "flips to `reply:` when the run ends — usually within a minute."
    )
    batch.updates.append({
        "id": rem.id, "name": f"sent: {text}", "body": _status_body(entry, "working", status, []),
    })
    activity_module.record(_LIST, "manager-sent", "", f"entry={entry} chars={len(text)}")


def _poll(rem: reminders_module.Reminder, entry: int, book: dict, batch) -> None:
    after = [e for e in book["entries"] if e["id"] > entry]
    nxt = next((e for e in after if e["role"] == "person"), None)
    mine = [e for e in after if e["role"] != "person" and (nxt is None or e["id"] < nxt["id"])]
    done = nxt is not None or not book["working"]
    lines = _render(mine)
    if done:
        first = next((e["text"].splitlines()[0] for e in mine if e["role"] == "manager"), "")
        state, status = "done", f"Done {_now()}. Full reply below."
        title = f"reply: {first[:120]}" if first else "reply: (manager said nothing)"
    else:
        state, status = "working", f"Manager still working as of {_now()}. Steps so far below."
        title = rem.name
    body = _status_body(entry, state, status, lines)
    patch: dict = {"id": rem.id}
    if rem.body != body:
        patch["body"] = body
    if rem.name != title:
        patch["name"] = title
    if len(patch) > 1:
        batch.updates.append(patch)
    if done:
        activity_module.record(_LIST, "manager-reply", "", f"entry={entry} steps={len(mine)}")


def sync() -> None:
    if not _TOKEN_PATH.exists():  # deckhand not installed on this Mac — lane is inert
        return
    reminders_module.create_list(_LIST)
    remote = reminders_module.list_reminders(_LIST)
    batch = reminders_module.Batch()
    if not any(r.name == _HEADER for r in remote):
        batch.creates.append({"name": _HEADER, "body": _HEADER_BODY, "priority": 0})
    pending = [r for r in remote if r.name != _HEADER and not r.completed and not _ACK_RE.match(r.name)]
    working = []
    for r in remote:
        m = _TAG_RE.search(r.body)
        if m and m.group("state") == "working":
            working.append((r, int(m.group("entry"))))
    if working:
        try:
            book = _call(f"/manager?since={min(e for _, e in working) - 1}")
        except (OSError, urllib.error.URLError, ValueError) as e:
            log.warning("manager poll failed: %s", e)
        else:
            for r, entry in working:
                _poll(r, entry, book, batch)
    for r in pending:
        _send(r, batch)
    if not batch.empty():
        reminders_module.apply_batch(_LIST, batch)
