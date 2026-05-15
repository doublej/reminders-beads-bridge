"""Default-list mirror reminder for voice mailbox discoverability."""

import logging
import re

from . import reminders as reminders_module

log = logging.getLogger(__name__)

_MIRROR_RE = re.compile(r'<bb:mirror slug="([a-z0-9][a-z0-9-]*)"/>')
_EXCERPT_LINES = 6


def _default_list_name() -> str | None:
    store = reminders_module.get_store()
    cal = store.defaultCalendarForNewReminders()
    return str(cal.title()) if cal else None


def _title(slug: str) -> str:
    return f"Voice exchange open: {slug}"


def _body(slug: str, list_name: str, brief_text: str) -> str:
    head = [ln for ln in brief_text.strip().splitlines() if ln.strip()][:_EXCERPT_LINES]
    excerpt = "\n".join(head) or "(empty brief)"
    return (
        f"Voice exchange open — slug {slug}\n\n"
        f"Agent brief is in the list: {list_name}\n\n"
        f"Drain your responses back into the agent:\n"
        f"  rbridge mailbox read --slug {slug}\n\n"
        f"Brief excerpt:\n{excerpt}\n\n"
        f'<bb:mirror slug="{slug}"/>'
    )


def _find(slug: str) -> tuple[str, reminders_module.Reminder] | None:
    ln = _default_list_name()
    if not ln:
        return None
    for r in reminders_module.list_reminders(ln):
        m = _MIRROR_RE.search(r.body)
        if m and m.group(1) == slug:
            return ln, r
    return None


def upsert(slug: str, list_name: str, brief_text: str) -> bool:
    ln = _default_list_name()
    if not ln:
        log.warning("no default reminders list; mirror skipped for %s", slug)
        return False
    title = _title(slug)
    body = _body(slug, list_name, brief_text)
    found = _find(slug)
    batch = reminders_module.Batch()
    if found is None:
        batch.creates.append({"name": title, "body": body, "priority": 1})
    else:
        _, r = found
        if r.name != title or r.body != body or r.priority != 1:
            batch.updates.append(
                {"id": r.id, "name": title, "body": body, "priority": 1}
            )
    if batch.empty():
        return True
    reminders_module.apply_batch(ln, batch)
    return True


def delete(slug: str) -> bool:
    found = _find(slug)
    if found is None:
        return False
    ln, r = found
    batch = reminders_module.Batch()
    batch.deletes.append(r.id)
    reminders_module.apply_batch(ln, batch)
    return True
