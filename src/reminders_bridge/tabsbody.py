"""Body composition + send-region parsing for the Claude: Tabs lane.

Isolates all reminder-body string concerns (peer to `body.py` for beads).
The body is daemon-owned and overwritten each cycle; the only thing read back
is the free text under `send:`. A non-empty `send:` payload is typed into the
live tab when the reminder is completed — payload + completion must land in the
same write, since the daemon reads both from one polled snapshot and unchecks a
completed reminder every cycle.
"""

import re

from . import ghostty as ghostty_module
from . import transcript as transcript_module

_SEND_RE = re.compile(r"(?mi)^[ \t]*send:[ \t]*")
_EXPAND_RE = re.compile(r"(?mi)^[ \t]*expand:[ \t]*$")
_COLLAPSE_RE = re.compile(r"(?mi)^[ \t]*collapse:[ \t]*$")
_HELP = (
    "SEND = write under `send:` AND complete this reminder in one action — the "
    "completion is the trigger. Agents: set the text and `completed: true` in a "
    "single update; completing first sends empty. STAGE = write under `send:` and "
    "leave it unchecked (just a draft). On send the bridge switches Ghostty to "
    "this tab and types the message in. "
    "(Needs the tab on the active Space + Accessibility permission for the bridge.)\n"
    "EXPAND = add a line `expand:` (unchecked, no completion needed) to swap the "
    "transcript for the full recent session; `collapse:` shrinks it back."
)


def title(tab: ghostty_module.Tab, session: "transcript_module.Session | None") -> str:
    name = session.title if session and session.title else tab.project
    return f"{name} · {tab.tty}"


def parse_send(body: str) -> str:
    parts = _SEND_RE.split(body)
    if len(parts) <= 1:
        return ""
    # Drop bare control-verb lines so `expand:`/`collapse:` are never typed into
    # the live tab, even if the agent writes them inside the send region.
    kept = [
        ln for ln in parts[-1].splitlines()
        if not _EXPAND_RE.match(ln) and not _COLLAPSE_RE.match(ln)
    ]
    return "\n".join(kept).strip()


def parse_controls(body: str) -> str:
    """Return the transcript control the agent requested: 'collapse' | 'expand' |
    ''. `collapse:` wins over `expand:` when both are present (explicit shrink)."""
    if _COLLAPSE_RE.search(body):
        return "collapse"
    if _EXPAND_RE.search(body):
        return "expand"
    return ""


def _render_turns(turns: list[dict]) -> str:
    if not turns:
        return "(nothing sent yet)"
    return "\n\n".join(f"you ({t['ts']}):\n{t['text']}" for t in turns)


def compose(
    tab: ghostty_module.Tab,
    session: "transcript_module.Session | None",
    turns: list[dict],
    carry_send: str = "",
    last_error: str = "",
    expanded: bool = False,
) -> str:
    sid = session.session_id if session else "-"
    status = session.status if session and session.status else "?"
    name = session.title if session and session.title else "(untitled)"
    if not session:
        tail, header = "(no session)", "──── transcript (live · read-only) ────"
    elif expanded:
        tail = transcript_module.render_tail(
            session.path, max_msgs=15, max_chars=2000, last_max_chars=6000, flatten=False
        )
        header = "──── transcript (live · read-only · EXPANDED — write `collapse:` to shrink) ────"
    else:
        tail = transcript_module.render_tail(session.path)
        header = "──── transcript (live · read-only · write `expand:` for the full session) ────"
    lines = [
        f"tab: {name}",
        f"project: {tab.project}    status: {status}",
        f"cwd: {tab.cwd}",
        f"tty: {tab.tty}    pid: {tab.pid}    mode: {tab.mode}",
        f"session: {sid}",
        "",
        header,
        tail,
        "",
        "──── sent ────",
        _render_turns(turns),
    ]
    if last_error:
        lines += ["", f"⚠ couldn't type into tab: {last_error}", "  message kept below — re-check the circle to retry."]
    lines += ["", "──── send ────", _HELP, "send:"]
    if carry_send:
        lines.append(carry_send)
    return "\n".join(lines).rstrip() + "\n"
