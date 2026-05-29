"""Resolve a cwd to its newest Claude Code session jsonl and render a tail.

Mirrors Claude Code's on-disk layout: `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`.
The encoding replaces `/`, `.`, and `_` with `-` (verified against the live
projects dir — dotted segments like `.claude-worktrees` become `--claude-...`).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

_PROJECTS_DIR = Path.home() / ".claude" / "projects"
_ENCODE_RE = re.compile(r"[/._]")


@dataclass
class Session:
    session_id: str
    path: str


def encode_cwd(cwd: str) -> str:
    return _ENCODE_RE.sub("-", cwd)


def resolve_session(cwd: str) -> Session | None:
    if not cwd:
        return None
    dir_ = _PROJECTS_DIR / encode_cwd(cwd)
    newest = _newest_jsonl(dir_)
    if newest is None:
        return None
    return Session(session_id=newest.stem, path=str(newest))


def _newest_jsonl(dir_: Path) -> Path | None:
    try:
        files = [p for p in dir_.iterdir() if p.suffix == ".jsonl"]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text" and part.get("text"):
            parts.append(str(part["text"]).strip())
        elif kind == "tool_use":
            parts.append(f"[tool: {part.get('name', '?')}]")
        elif kind == "tool_result":
            parts.append("[tool result]")
    return "\n".join(p for p in parts if p)


def render_tail(path: str, max_msgs: int = 6, max_chars: int = 400) -> str:
    msgs: list[str] = []
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return "(transcript unavailable)"
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _text_of(msg.get("content"))
        if text:
            msgs.append(f"{role}: {_clip(text, max_chars)}")
    if not msgs:
        return "(no messages yet)"
    return "\n\n".join(msgs[-max_msgs:])


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
