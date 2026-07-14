"""Reminder body syntax: XML-tagged, lintable, note-preserving."""

import dataclasses
import datetime as _dt
import re
from collections.abc import Callable

from . import beads as beads_module

_META_RE = re.compile(
    r"<bb:meta>\[(?P<type>[^\s\]]+)\s·\sp(?P<prio>\d)\s·\s(?P<status>[^\]]+)\]</bb:meta>"
)
_DESC_RE = re.compile(r"<bb:desc>\n(?P<body>.*?)\n</bb:desc>", re.DOTALL)
_NOTES_RE = re.compile(r"<bb:notes>\n(?P<body>.*?)\n</bb:notes>", re.DOTALL)
_RESTORED_RE = re.compile(
    r'<bb:restored at="[^"]+">[^<]*</bb:restored>\n\n', re.DOTALL
)
_AGENT_MARKER_RE = re.compile(
    r"^[ \t]*!agent(?:[ \t]+(?P<args>[^\n]*?))?[ \t]*$", re.MULTILINE
)

VALID_STATUSES = {"open", "in_progress", "hooked", "blocked", "closed", "ready", "waiting"}


@dataclasses.dataclass
class Parsed:
    meta_type: str | None
    meta_prio: int | None
    meta_status: str | None
    description: str | None
    notes: str
    had_restored_banner: bool


@dataclasses.dataclass
class LintIssue:
    code: str
    message: str


def parse(body: str) -> Parsed:
    meta = _META_RE.search(body)
    desc = _DESC_RE.search(body)
    notes = _NOTES_RE.search(body)
    return Parsed(
        meta_type=meta.group("type") if meta else None,
        meta_prio=int(meta.group("prio")) if meta else None,
        meta_status=meta.group("status") if meta else None,
        description=desc.group("body") if desc else None,
        notes=notes.group("body") if notes else "",
        had_restored_banner=bool(_RESTORED_RE.search(body)),
    )


def _expected_meta(issue: beads_module.Issue) -> str:
    return f"<bb:meta>[{issue.issue_type} · p{issue.priority} · {issue.status}]</bb:meta>"


def _tampered(parsed: Parsed, issue: beads_module.Issue) -> bool:
    return (parsed.description or "") != (issue.description or "")


def compose(issue: beads_module.Issue, current: str | None = None) -> str:
    notes = ""
    restore = False
    if current:
        parsed = parse(current)
        notes = parsed.notes
        missing = parsed.meta_type is None or parsed.description is None
        if missing or _tampered(parsed, issue):
            restore = not (parsed.meta_type is None and parsed.description is None and not notes)
    parts: list[str] = []
    if restore:
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        parts.append(
            f'<bb:restored at="{ts}">Structure was overwritten. '
            f"Ticket restored from beads; notes preserved below.</bb:restored>"
        )
    parts.append(_expected_meta(issue))
    parts.append(f"<bb:desc>\n{issue.description or ''}\n</bb:desc>")
    parts.append(f"<bb:notes>\n{notes}\n</bb:notes>")
    return "\n\n".join(parts)


def append_note(body: str, text: str) -> str | None:
    """Append `text` inside the `<bb:notes>` block, preserving every other block.

    The daemon-owned, tamper-safe way to add to a bead's notes (used by the
    command lane) — the agent never has to read-modify-write the whole opaque
    body. Returns None if there is no `<bb:notes>` block (caller acks an error
    rather than risk corrupting the body). Never raises.
    """
    m = _NOTES_RE.search(body)
    if not m:
        return None
    existing = m.group("body")
    joined = f"{existing}\n{text}" if existing.strip() else text
    return f"{body[: m.start()]}<bb:notes>\n{joined}\n</bb:notes>{body[m.end() :]}"


def consume_agent_markers(body: str, dispatch: Callable[[dict[str, str]], str]) -> str:
    """Replace each `!agent [args]` line in body via dispatch(parsed_args)→tag."""
    def _sub(m: re.Match) -> str:
        args: dict[str, str] = {}
        for tok in (m.group("args") or "").split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                args[k] = v
        return dispatch(args)
    return _AGENT_MARKER_RE.sub(_sub, body)


def lint(body: str, issue: beads_module.Issue | None = None) -> list[LintIssue]:
    issues: list[LintIssue] = []
    parsed = parse(body)
    if parsed.meta_type is None:
        issues.append(LintIssue("missing-meta", "no <bb:meta> tag"))
    elif parsed.meta_status not in VALID_STATUSES:
        issues.append(LintIssue("bad-status", f"unknown status {parsed.meta_status!r}"))
    if parsed.description is None:
        issues.append(LintIssue("missing-desc", "no <bb:desc> tag"))
    if _NOTES_RE.search(body) is None:
        issues.append(LintIssue("missing-notes", "no <bb:notes> tag"))
    if issue is not None and parsed.meta_type is not None:
        meta_drift = (
            parsed.meta_type != issue.issue_type
            or parsed.meta_prio != issue.priority
            or parsed.meta_status != issue.status
        )
        if meta_drift or _tampered(parsed, issue):
            issues.append(LintIssue("drift", f"body diverges from bead {issue.id}"))
    return issues
