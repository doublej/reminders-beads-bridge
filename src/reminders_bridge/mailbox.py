"""Voice exchange mailboxes — free-floating Reminders lists for agent ↔ user."""

import datetime as _dt
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import activity as activity_module
from . import atomicio as atomicio_module
from . import mirror as mirror_module
from . import navigation as navigation_module
from . import reminders as reminders_module

log = logging.getLogger(__name__)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
HEADER_TITLE = "How this list works"
_STATE_DIR = Path(
    os.getenv("RBRIDGE_MAILBOX_DIR", "~/.claude/voice-mailboxes")
).expanduser()

# Pre-rename voice-list prefix. Daemon deletes any matching list on
# startup — see `_gc_legacy_lists`. Voice flow has nothing to do with
# beads, so the `Beads: ` prefix was misleading.
_LEGACY_VOICE_LIST_PREFIX = "Beads: Voice: "


def _voice_prefix() -> str:
    return os.getenv("RBRIDGE_VOICE_LIST_PREFIX", "_rb_voice_")


def voice_list_prefix() -> str:
    """Full prefix for voice exchange list names (default ``_rb_voice_``)."""
    return _voice_prefix()


# Prefixes that have ever named a voice list — the active default plus the
# two pre-rename forms. Existing exchanges store their list name in state, so
# they keep working under the old prefix; this set keeps the project-hide path
# from ever deleting any of them.
def _voice_prefixes() -> tuple[str, ...]:
    return (voice_list_prefix(), "Voice: ", _LEGACY_VOICE_LIST_PREFIX)


def is_voice_list_name(name: str) -> bool:
    return any(name.startswith(p) for p in _voice_prefixes())


def list_name_for(slug: str) -> str:
    return f"{voice_list_prefix()}{slug}"


HEADER_BODY_TEMPLATE = """\
Voice exchange mailbox — slug: {slug}
Brief saved at: {brief_path}

Drain your responses into the project agent (run this in your terminal):
  rbridge mailbox read --slug {slug}

Close the exchange:
  - Add a reminder titled `done` (daemon auto-closes next cycle), OR
  - Run: rbridge mailbox close --slug {slug}

When you reply, add new reminders to this list. Optional title prefixes:
  decision: <text>   you committed to something
  note: <text>       observation / context
  question: <text>   you expect the project agent to answer
  deferred: <text>   talked about it, punted; revisit later
  done               close the exchange

This reminder is daemon-owned; edits get overwritten."""


NAV_HELP = """

File navigation (this exchange is rooted at a repo):
  fetch: <path>          read a file, relative to the repo root
  fetch: <path> page 2   next chunk of a long file
  grep: <term>           search file contents under the root
  tree: <subdir>         list a directory (omit subdir for the root)
The daemon answers in place: your `fetch:` becomes `file:` with the
contents in the body, left unchecked. Refused requests become `blocked:`."""


@dataclass
class Mailbox:
    slug: str
    list_name: str
    brief_path: str
    created_at: str
    kind: str
    source_cwd: str = ""


@dataclass
class CloseResult:
    found: bool
    list_deleted: bool = False
    list_was_missing: bool = False
    list_error: str | None = None
    mirror_error: str | None = None
    state_deleted: bool = False


def _state_path(slug: str) -> Path:
    return _STATE_DIR / f"{slug}.json"


def _brief_path(slug: str) -> Path:
    return _STATE_DIR / f"{slug}.brief.md"


def _validate(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise ValueError(
            f"invalid slug {slug!r}; expected [a-z0-9][a-z0-9-]{{0,47}}"
        )


def _load(slug: str) -> Mailbox | None:
    p = _state_path(slug)
    if not p.exists():
        return None
    try:
        return Mailbox(**json.loads(p.read_text()))
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def _save(mb: Mailbox) -> None:
    atomicio_module.atomic_write_text(
        _state_path(mb.slug), json.dumps(asdict(mb), indent=2)
    )


def _delete_state(slug: str) -> None:
    _state_path(slug).unlink(missing_ok=True)
    _brief_path(slug).unlink(missing_ok=True)


def list_active() -> list[Mailbox]:
    if not _STATE_DIR.exists():
        return []
    out: list[Mailbox] = []
    for f in sorted(_STATE_DIR.glob("*.json")):
        try:
            out.append(Mailbox(**json.loads(f.read_text())))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return out


def _list_exists(name: str) -> bool:
    store = reminders_module.get_store()
    return reminders_module._find_calendar(store, name) is not None


def _mirror_enabled() -> bool:
    return os.getenv("RBRIDGE_MAILBOX_MIRROR", "true").lower() not in {
        "false", "0", "no",
    }


def _rewrite_reminders(mb: Mailbox, brief_text: str) -> None:
    reminders_module.create_list(mb.list_name)
    remote = reminders_module.list_reminders(mb.list_name)
    header_body = HEADER_BODY_TEMPLATE.format(
        slug=mb.slug, brief_path=mb.brief_path
    )
    if navigation_module.is_active(mb):
        header_body += NAV_HELP
    brief_title = f"Brief for {mb.slug}"
    batch = reminders_module.Batch()
    header = next((r for r in remote if r.name == HEADER_TITLE), None)
    if header is None:
        batch.creates.append(
            {"name": HEADER_TITLE, "body": header_body, "priority": 1}
        )
    elif header.body != header_body or header.priority != 1:
        batch.updates.append(
            {"id": header.id, "body": header_body, "priority": 1}
        )
    brief = next((r for r in remote if r.name == brief_title), None)
    if brief is None:
        batch.creates.append(
            {"name": brief_title, "body": brief_text, "priority": 1}
        )
    elif brief.body != brief_text or brief.priority != 1:
        batch.updates.append(
            {"id": brief.id, "body": brief_text, "priority": 1}
        )
    if not batch.empty():
        reminders_module.apply_batch(mb.list_name, batch)


def open_mailbox(
    slug: str, kind: str, brief_text: str, source_cwd: str = ""
) -> Mailbox:
    _validate(slug)
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    brief_p = _brief_path(slug)
    atomicio_module.atomic_write_text(brief_p, brief_text)
    existing = _load(slug)
    if existing is not None:
        mb = existing
        mb.brief_path = str(brief_p)
        mb.kind = kind or mb.kind
        if source_cwd:
            mb.source_cwd = source_cwd
    else:
        mb = Mailbox(
            slug=slug,
            list_name=list_name_for(slug),
            brief_path=str(brief_p),
            created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(
                timespec="seconds"
            ),
            kind=kind,
            source_cwd=source_cwd,
        )
    _save(mb)
    _rewrite_reminders(mb, brief_text)
    if _mirror_enabled():
        try:
            mirror_module.upsert(slug, mb.list_name, brief_text)
        except RuntimeError as e:
            log.warning("mirror upsert failed for %s: %s", slug, e)
    if existing is None:
        activity_module.record(mb.list_name, "voice-opened", "", mb.slug)
    return mb


# Title prefixes owned by the file-navigation lane (requests + served + refused).
# These are agent<->daemon plumbing, never user->project-agent responses, so
# `read()` filters them out.
_NAV_PREFIXES = (
    "fetch:", "grep:", "tree:", "file:", "results:", "listing:", "blocked:",
)


def _classify(title: str) -> tuple[str, str]:
    low = title.lower().strip()
    if low == "done":
        return "done", ""
    for kind in ("decision", "note", "question", "deferred"):
        if low.startswith(f"{kind}:"):
            return kind, title.split(":", 1)[1].strip()
    return "free", title


def read(slug: str) -> dict:
    mb = _load(slug)
    if mb is None:
        raise RuntimeError(f"no mailbox for slug {slug!r}")
    rems = reminders_module.list_reminders(mb.list_name)
    responses = []
    has_done = False
    brief_title = f"Brief for {mb.slug}"
    for r in rems:
        if r.name in (HEADER_TITLE, brief_title):
            continue
        if r.name.strip().lower().startswith(_NAV_PREFIXES):
            continue
        kind, text = _classify(r.name)
        if kind == "done":
            has_done = True
        responses.append(
            {
                "id": r.id,
                "kind": kind,
                "title": text or r.name,
                "body": r.body,
                "completed": r.completed,
            }
        )
    return {
        "slug": mb.slug,
        "list_name": mb.list_name,
        "brief_path": mb.brief_path,
        "kind": mb.kind,
        "created_at": mb.created_at,
        "source_cwd": mb.source_cwd,
        "has_done": has_done,
        "responses": responses,
    }


def close(slug: str, reason: str = "user") -> CloseResult:
    mb = _load(slug)
    if mb is None:
        return CloseResult(found=False)
    result = CloseResult(found=True)
    try:
        if reminders_module.delete_list(mb.list_name):
            result.list_deleted = True
        else:
            result.list_was_missing = True
    except RuntimeError as e:
        result.list_error = str(e)
        log.warning("delete list failed for %s: %s", slug, e)
    try:
        mirror_module.delete(slug)
    except RuntimeError as e:
        result.mirror_error = str(e)
        log.warning("mirror delete failed for %s: %s", slug, e)
    _delete_state(slug)
    result.state_deleted = True
    activity_module.record(mb.list_name, "voice-closed", "", f"{slug} ({reason})")
    return result


def refresh(slug: str) -> bool:
    mb = _load(slug)
    if mb is None:
        return False
    brief_p = Path(mb.brief_path)
    brief_text = brief_p.read_text() if brief_p.exists() else ""
    _rewrite_reminders(mb, brief_text)
    if _mirror_enabled():
        mirror_module.upsert(slug, mb.list_name, brief_text)
    return True


def _sync_one(mb: Mailbox) -> None:
    if not _list_exists(mb.list_name):
        log.info("mailbox %s: list deleted externally; cleaning state", mb.slug)
        try:
            mirror_module.delete(mb.slug)
        except RuntimeError:
            pass
        _delete_state(mb.slug)
        activity_module.record(
            mb.list_name, "voice-closed", "", f"{mb.slug} (list-deleted)"
        )
        return
    brief_p = Path(mb.brief_path)
    brief_text = (
        brief_p.read_text() if brief_p.exists() else f"(brief missing: {mb.brief_path})"
    )
    _rewrite_reminders(mb, brief_text)
    rems = reminders_module.list_reminders(mb.list_name)
    for r in rems:
        if not r.completed and r.name.strip().lower() == "done":
            activity_module.record(
                mb.list_name, "voice-response", "", f"{mb.slug}: done"
            )
            close(mb.slug, reason="done-reminder")
            return
    batch = navigation_module.serve_requests(mb, rems)
    if not batch.empty():
        reminders_module.apply_batch(mb.list_name, batch)


def _gc_legacy_lists() -> None:
    """Delete pre-rename `Beads: Voice: *` lists if any survive.

    Voice exchanges used to live under `Beads: <voice-prefix><slug>` but
    the flow is independent of beads — the prefix was misleading. Any
    list still carrying the old prefix is orphan after the rename
    (state files have been migrated to the new naming convention or
    cleared). Drop them.
    """
    for name in reminders_module.list_calendar_names():
        if not name.startswith(_LEGACY_VOICE_LIST_PREFIX):
            continue
        try:
            if reminders_module.delete_list(name):
                log.info("GC'd legacy voice list: %s", name)
        except RuntimeError as e:
            log.warning("legacy GC failed for %s: %s", name, e)


def sync() -> None:
    try:
        _gc_legacy_lists()
    except Exception as e:
        log.warning("legacy voice-list GC failed: %s", e)
    for mb in list_active():
        try:
            _sync_one(mb)
        except Exception as e:
            log.warning("mailbox sync failed for %s: %s", mb.slug, e)
