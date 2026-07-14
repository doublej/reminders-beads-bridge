"""Resolve a live Claude Code tab to its session: id, jsonl, title, status.

Two on-disk sources, keyed differently:
- `~/.claude/sessions/<pid>.json` — authoritative per-pid record (sessionId,
  cwd, status, name). Present for most interactive tabs.
- `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` — the transcript. Its
  `aiTitle` is the title Claude paints onto the Ghostty tab (the key we match
  against the tab bar). Encoding replaces `/`, `.`, `_` with `-`.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

_HOME = Path.home()
_SESSIONS_DIR = _HOME / ".claude" / "sessions"
_PROJECTS_DIR = _HOME / ".claude" / "projects"
_ENCODE_RE = re.compile(r"[/._]")
_AITITLE_RE = re.compile(r'"aiTitle":"((?:[^"\\]|\\.)*)"')


@dataclass
class Session:
    session_id: str
    path: str
    title: str
    status: str
    cwd: str


def encode_cwd(cwd: str) -> str:
    return _ENCODE_RE.sub("-", cwd)


def _session_file(pid: int) -> dict:
    try:
        return json.loads((_SESSIONS_DIR / f"{pid}.json").read_text())
    except (OSError, ValueError):
        return {}


def _jsonl_path(cwd: str, session_id: str) -> Path:
    return _PROJECTS_DIR / encode_cwd(cwd) / f"{session_id}.jsonl"


def _newest_jsonl(cwd: str) -> Path | None:
    try:
        files = [p for p in (_PROJECTS_DIR / encode_cwd(cwd)).iterdir() if p.suffix == ".jsonl"]
    except OSError:
        return None
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def resolve(pid: int, cwd: str) -> Session | None:
    meta = _session_file(pid)
    sid = meta.get("sessionId", "")
    cwd = meta.get("cwd") or cwd
    if sid and cwd:
        path = _jsonl_path(cwd, sid)
    else:
        newest = _newest_jsonl(cwd)
        if newest is None:
            return None
        path, sid = newest, newest.stem
    title = ai_title(path) or (meta.get("name") or "")
    return Session(sid, str(path), title, meta.get("status", ""), cwd)


def ai_title(path: Path) -> str:
    """Last `aiTitle` in the jsonl — the title Claude paints on the tab."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    matches = _AITITLE_RE.findall(text)
    return matches[-1].encode().decode("unicode_escape") if matches else ""


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


def render_tail(
    path: str, max_msgs: int = 6, max_chars: int = 400, last_max_chars: int = 2000
) -> str:
    """Recent user/assistant turns. The latest turn gets `last_max_chars` — a
    review's conclusion (the whole reason to glance at a tab) used to be clipped
    to 400 chars and decapitated; older turns stay at `max_chars` so scrollback
    stays compact."""
    rows: list[tuple[str, str]] = []
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
        if msg.get("role") not in ("user", "assistant"):
            continue
        text = _text_of(msg.get("content"))
        if text:
            rows.append((str(msg["role"]), text))
    if not rows:
        return "(no messages yet)"
    recent = rows[-max_msgs:]
    last = len(recent) - 1
    return "\n\n".join(
        f"{role}: {_clip(text, last_max_chars if i == last else max_chars)}"
        for i, (role, text) in enumerate(recent)
    )


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
