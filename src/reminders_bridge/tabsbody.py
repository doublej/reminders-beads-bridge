"""Body composition + send-region parsing for the Claude: Tabs lane.

Isolates all reminder-body string concerns (peer to `body.py` for beads).
The body is daemon-owned and overwritten each cycle; the only thing read back
is the free text under `send:`, consumed when the reminder is completed.
"""

import re

from . import ghostty as ghostty_module

_SEND_RE = re.compile(r"(?mi)^[ \t]*send:[ \t]*")
_HELP = (
    "Type a message under `send:`, then tap the circle to send. The bridge "
    "forks this session and posts the reply above. It does not type into the live tab."
)


def title(tab: ghostty_module.Tab) -> str:
    return f"{tab.project} · {tab.tty}"


def parse_send(body: str) -> str:
    parts = _SEND_RE.split(body)
    return parts[-1].strip() if len(parts) > 1 else ""


def _render_turns(turns: list[dict], busy: bool) -> str:
    if not turns and not busy:
        return "(no messages yet)"
    lines = [f"{t['role']} ({t['ts']}):\n{t['text']}" for t in turns]
    if busy:
        lines.append("claude: replying…")
    return "\n\n".join(lines)


def compose(
    tab: ghostty_module.Tab, sid: str, tail: str, turns: list[dict], busy: bool
) -> str:
    return "\n".join([
        f"project: {tab.project}",
        f"cwd: {tab.cwd}",
        f"tty: {tab.tty}    pid: {tab.pid}    mode: {tab.mode}",
        f"session: {sid or '-'}",
        "",
        "──── transcript (live · read-only) ────",
        tail,
        "",
        "──── messages ────",
        _render_turns(turns, busy),
        "",
        "──── send ────",
        _HELP,
        "send:",
    ]).rstrip() + "\n"
