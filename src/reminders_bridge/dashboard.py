"""Dashboard address: a rotating token + the `_rb_dashboard` URL reminder.

The token is a time-windowed HMAC of a shared secret, so the daemon (which
surfaces the live URL in a reminder here) and `rbridge serve` (which validates
it) compute the same value independently — no coordination beyond the secret
file. `valid()` accepts the current and previous window to tolerate rollover.

The URL reminder is the agent's entry point: `docs/AGENT.md` tells the agent to
open it; the rotating token never has to live in static docs.
"""

import hashlib
import hmac
import os
import secrets
import socket
import time
from pathlib import Path

from . import reminders as reminders_module

_LIST_NAME = os.getenv("RBRIDGE_DASHBOARD_LIST", "_rb_dashboard")
_TITLE = "Bridge dashboard"
_SECRET_PATH = Path(
    os.getenv(
        "RBRIDGE_DASHBOARD_SECRET_FILE",
        "~/.claude/reminders-bridge-dashboard-secret",
    )
).expanduser()


def list_name() -> str:
    return _LIST_NAME


def host() -> str:
    return os.getenv("RBRIDGE_DASHBOARD_HOST", "127.0.0.1")


def port() -> int:
    return int(os.getenv("RBRIDGE_DASHBOARD_PORT", "47900"))


def _window_s() -> int:
    return max(60, int(os.getenv("RBRIDGE_DASHBOARD_WINDOW_S", "900")))


def _secret() -> bytes:
    env = os.getenv("RBRIDGE_DASHBOARD_SECRET")
    if env:
        return env.encode()
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_text().strip().encode()
    token = secrets.token_hex(32)
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_PATH.write_text(token)
    _SECRET_PATH.chmod(0o600)
    return token.encode()


def _token_for(window: int) -> str:
    return hmac.new(_secret(), str(window).encode(), hashlib.sha256).hexdigest()[:16]


def current_token() -> str:
    return _token_for(int(time.time()) // _window_s())


def valid(token: str) -> bool:
    if not token:
        return False
    now_window = int(time.time()) // _window_s()
    return any(
        hmac.compare_digest(token, _token_for(w))
        for w in (now_window, now_window - 1)
    )


def url(token: str | None = None) -> str:
    return f"http://{host()}:{port()}/?t={token or current_token()}"


def _alive() -> bool:
    try:
        with socket.create_connection((host(), port()), timeout=0.3):
            return True
    except OSError:
        return False


def _body() -> str:
    lines = [url()]
    if not _alive():
        lines += ["", "(server not running — start it with: rbridge serve)"]
    lines += [
        "",
        "At-a-glance view of the bridge: projects, bead counts, recent activity.",
        "Read-only — actions go through rbridge.",
        f"Token rotates ~every {_window_s() // 60} min; reopen this reminder for a fresh link.",
    ]
    return "\n".join(lines)


def sync() -> None:
    ln = list_name()
    reminders_module.create_list(ln)
    remote = reminders_module.list_reminders(ln)
    body = _body()
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
