"""Serve fetch/grep/tree requests for voice mailboxes.

A request reminder titled `fetch:`/`grep:`/`tree:` is executed against the
mailbox's repo root and rewritten in place: title verb->noun (`fetch:`->`file:`),
result in the body, left unchecked. The title rewrite is the loop guard — next
cycle the verb regex no longer matches (cf. the `!agent` inert-tag pattern in
body.py). No state file: a crash mid-serve just re-serves deterministically.
"""

import re
from pathlib import Path

from . import activity as activity_module
from . import reminders as reminders_module
from . import sandbox

_VERB_RE = re.compile(
    r"^(?P<verb>fetch|grep|tree)\s*:\s*(?P<arg>.*)$", re.IGNORECASE | re.DOTALL
)
_PAGE_RE = re.compile(r"\s+page\s+(\d+)\s*$", re.IGNORECASE)


def is_active(mb) -> bool:
    """True when this mailbox has a usable repo root and nav is not killed."""
    return _root(mb) is not None


def serve_requests(mb, reminders) -> reminders_module.Batch:
    """Build an in-place-update Batch for any pending nav request reminders."""
    batch = reminders_module.Batch()
    root = _root(mb)
    if root is None:
        return batch
    for r in reminders:
        served = _maybe_serve(mb, root, r)
        if served is not None:
            batch.updates.append({"id": r.id, "name": served[0], "body": served[1]})
    return batch


def _root(mb) -> Path | None:
    if not sandbox.nav_enabled():
        return None
    root_str = (getattr(mb, "source_cwd", "") or "").strip()
    if not root_str:
        return None
    root = Path(root_str).expanduser()
    return root if root.is_dir() else None


def _maybe_serve(mb, root: Path, r) -> tuple[str, str] | None:
    if r.completed:
        return None
    m = _VERB_RE.match(r.name.strip())
    if not m:
        return None
    verb, arg = m.group("verb").lower(), m.group("arg").strip()
    try:
        result = _dispatch(root, verb, arg)
        activity_module.record(mb.list_name, "voice-nav", "", f"{mb.slug}: {verb} {arg}")
        return result
    except sandbox.NavError as e:
        activity_module.record(
            mb.list_name, "voice-nav-blocked", "", f"{mb.slug}: {verb} {arg} — {e}"
        )
        return f"blocked: {arg}", _refusal(root, str(e))


def _dispatch(root: Path, verb: str, arg: str) -> tuple[str, str]:
    if verb == "fetch":
        relpath, page = _split_page(arg)
        text = _read_file(sandbox.safe_resolve(root, relpath), page)
        suffix = f" page {page}" if page > 1 else ""
        return f"file: {relpath}{suffix}", text
    if verb == "grep":
        return f"results: {arg}", _grep(root, arg)
    sub = arg or "."
    return f"listing: {sub}", _tree(sandbox.safe_resolve(root, sub))


def _split_page(arg: str) -> tuple[str, int]:
    m = _PAGE_RE.search(arg)
    if not m:
        return arg, 1
    return arg[: m.start()].strip(), max(int(m.group(1)), 1)


def _read_file(path: Path, page: int) -> str:
    if not path.exists():
        raise sandbox.NavError("not found")
    if path.is_dir():
        raise sandbox.NavError("is a directory — use tree:")
    if path.suffix.lower() in sandbox.BINARY_SUFFIXES:
        raise sandbox.NavError("binary file type")
    cap = sandbox.int_env("RBRIDGE_NAV_MAX_BYTES", 65536)
    with path.open("rb") as fh:
        fh.seek(max(page - 1, 0) * cap)
        raw = fh.read(cap + 1)
    data = raw[:cap]
    if b"\x00" in data:
        raise sandbox.NavError("not a text file")
    text = data.decode("utf-8", errors="replace")
    if len(raw) > cap:
        text += f"\n\n--- truncated at {cap} bytes; request page {page + 1} for more ---"
    return text


def _grep(root: Path, term: str) -> str:
    if not term:
        raise sandbox.NavError("empty search term")
    cap = sandbox.int_env("RBRIDGE_NAV_GREP_HITS", 50)
    needle = term.lower()
    hits: list[str] = []
    for path in sandbox.walk_files(root):
        hits.extend(_scan(path, root, needle, cap - len(hits)))
        if len(hits) >= cap:
            break
    if not hits:
        return f'No matches for "{term}".'
    capped = " (capped — refine the term)" if len(hits) >= cap else ""
    return f'{len(hits)} match(es) for "{term}"{capped}:\n\n' + "\n".join(hits)


def _scan(path: Path, root: Path, needle: str, remaining: int) -> list[str]:
    out: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if needle in line.lower():
                    out.append(f"{path.relative_to(root)}:{n}:{line.strip()[:200]}")
                    if len(out) >= remaining:
                        break
    except OSError:
        return []
    return out


def _tree(start: Path) -> str:
    if not start.is_dir():
        raise sandbox.NavError("not a directory — use fetch:")
    cap = sandbox.int_env("RBRIDGE_NAV_TREE_ENTRIES", 200)
    depth = sandbox.int_env("RBRIDGE_NAV_TREE_DEPTH", 2)
    lines: list[str] = []
    _descend(start, 0, depth, cap, lines)
    if not lines:
        return "(empty)"
    if len(lines) >= cap:
        lines.append(f"--- capped at {cap} entries ---")
    return "\n".join(lines)


def _descend(d: Path, level: int, max_depth: int, cap: int, lines: list[str]) -> None:
    if level > max_depth or len(lines) >= cap:
        return
    try:
        entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return
    for e in entries:
        if len(lines) >= cap:
            return
        if sandbox.denied_component(e.name):
            continue
        indent = "  " * level
        if e.is_dir():
            lines.append(f"{indent}{e.name}/")
            _descend(e, level + 1, max_depth, cap, lines)
        else:
            lines.append(f"{indent}{e.name}")


def _refusal(root: Path, reason: str) -> str:
    return (
        f"Navigation refused: {reason}\n\n"
        f"Root: {root}\n"
        "(set RBRIDGE_VOICE_NAV=0 to disable file navigation)"
    )
