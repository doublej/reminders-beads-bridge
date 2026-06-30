"""EventKit-backed Reminders access (Python ↔ native macOS framework)."""

from dataclasses import dataclass, field
from typing import Any

import objc  # type: ignore[import-not-found]
from EventKit import (  # type: ignore[import-not-found]
    EKCalendar,
    EKEntityTypeReminder,
    EKEventStore,
    EKReminder,
    EKSourceTypeCalDAV,
    EKSourceTypeLocal,
)
from Foundation import NSDate, NSRunLoop  # type: ignore[import-not-found]


@dataclass
class Reminder:
    id: str
    name: str
    body: str
    completed: bool
    priority: int


@dataclass
class Batch:
    creates: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.creates or self.updates or self.deletes)


_RUN_MODE = "NSDefaultRunLoopMode"
_store: EKEventStore | None = None


def _spin(while_cond) -> None:
    # `runMode:beforeDate:` returns as soon as EventKit's completion source is
    # processed, so the timeout only caps idle sleep between checks — a wide
    # value adds no latency to the common (sub-ms callback) case but avoids
    # needless 50 Hz FFI wakeups while a slower async call (auth, commit) runs.
    loop = NSRunLoop.currentRunLoop()
    while while_cond():
        loop.runMode_beforeDate_(
            _RUN_MODE, NSDate.dateWithTimeIntervalSinceNow_(0.25)
        )


def autorelease_pool():
    return objc.autorelease_pool()


def reset_store() -> None:
    """Drop EventKit's internal object cache. Safe between sync cycles."""
    global _store
    if _store is not None:
        _store.reset()


def get_store() -> EKEventStore:
    global _store
    if _store is not None:
        return _store
    store = EKEventStore.alloc().init()
    state: dict[str, Any] = {"done": False, "granted": False, "err": None}

    def cb(granted, err):
        state["granted"] = bool(granted)
        state["err"] = err
        state["done"] = True

    if hasattr(store, "requestFullAccessToRemindersWithCompletion_"):
        store.requestFullAccessToRemindersWithCompletion_(cb)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeReminder, cb)

    _spin(lambda: not state["done"])
    if not state["granted"]:
        raise RuntimeError(
            "Reminders access denied. Grant in "
            "System Settings > Privacy & Security > Reminders."
        )
    _store = store
    return store


def _find_calendar(store: EKEventStore, name: str) -> EKCalendar | None:
    for cal in store.calendarsForEntityType_(EKEntityTypeReminder):
        if str(cal.title()) == name:
            return cal
    return None


def list_calendar_names() -> list[str]:
    store = get_store()
    return [
        str(cal.title())
        for cal in store.calendarsForEntityType_(EKEntityTypeReminder)
    ]


def _pick_source(store: EKEventStore):
    for src in store.sources():
        if src.sourceType() == EKSourceTypeCalDAV:
            return src
    for src in store.sources():
        if src.sourceType() == EKSourceTypeLocal:
            return src
    return store.defaultCalendarForNewReminders().source() if store.defaultCalendarForNewReminders() else None


def _fetch(store: EKEventStore, cal: EKCalendar) -> list[EKReminder]:
    predicate = store.predicateForRemindersInCalendars_([cal])
    state: dict[str, Any] = {"done": False, "items": []}

    def cb(items):
        state["items"] = list(items or [])
        state["done"] = True

    store.fetchRemindersMatchingPredicate_completion_(predicate, cb)
    _spin(lambda: not state["done"])
    return state["items"]


def create_list(name: str) -> None:
    store = get_store()
    if _find_calendar(store, name) is not None:
        return
    cal = EKCalendar.calendarForEntityType_eventStore_(EKEntityTypeReminder, store)
    cal.setTitle_(name)
    src = _pick_source(store)
    if src is None:
        raise RuntimeError("No Reminders source available")
    cal.setSource_(src)
    ok, err = store.saveCalendar_commit_error_(cal, True, None)
    if not ok:
        raise RuntimeError(f"saveCalendar failed: {err}")


def delete_list(name: str) -> bool:
    store = get_store()
    cal = _find_calendar(store, name)
    if cal is None:
        return False
    ok, err = store.removeCalendar_commit_error_(cal, True, None)
    if not ok:
        raise RuntimeError(f"removeCalendar failed: {err}")
    return True


def rename_list(old: str, new: str) -> bool:
    """Rename a list in place, preserving every reminder it holds.

    Used for lossless list migrations: renaming the calendar keeps the
    reminders (and the user state encoded in them — notes, completion,
    value bodies) intact. No-op if ``old`` is absent; refuses to clobber an
    existing ``new`` (returns False) so a half-migrated state can't merge
    two lists.
    """
    if old == new:
        return False
    store = get_store()
    cal = _find_calendar(store, old)
    if cal is None:
        return False
    if _find_calendar(store, new) is not None:
        return False
    cal.setTitle_(new)
    ok, err = store.saveCalendar_commit_error_(cal, True, None)
    if not ok:
        raise RuntimeError(f"rename {old!r}->{new!r} failed: {err}")
    return True


def _to_reminder(r: EKReminder) -> Reminder:
    return Reminder(
        id=str(r.calendarItemIdentifier()),
        name=str(r.title() or ""),
        body=str(r.notes() or ""),
        completed=bool(r.isCompleted()),
        priority=int(r.priority()),
    )


def list_reminders(list_name: str) -> list[Reminder]:
    store = get_store()
    cal = _find_calendar(store, list_name)
    if cal is None:
        return []
    return [_to_reminder(r) for r in _fetch(store, cal)]


def _apply_patch(r: EKReminder, patch: dict[str, Any]) -> None:
    if "name" in patch:
        r.setTitle_(patch["name"])
    if "body" in patch:
        r.setNotes_(patch["body"])
    if "completed" in patch:
        r.setCompleted_(bool(patch["completed"]))
    if "priority" in patch:
        r.setPriority_(int(patch["priority"]))


def apply_batch(list_name: str, batch: Batch) -> list[str]:
    if batch.empty():
        return []
    store = get_store()
    cal = _find_calendar(store, list_name)
    if cal is None:
        create_list(list_name)
        cal = _find_calendar(store, list_name)
        if cal is None:
            raise RuntimeError(f"List {list_name!r} could not be created")

    if batch.updates or batch.deletes:
        id_map = {
            str(r.calendarItemIdentifier()): r for r in _fetch(store, cal)
        }
    else:
        id_map = {}

    for u in batch.updates:
        r = id_map.get(u["id"])
        if r is None:
            continue
        _apply_patch(r, u)
        ok, err = store.saveReminder_commit_error_(r, False, None)
        if not ok:
            raise RuntimeError(f"saveReminder failed: {err}")

    for rid in batch.deletes:
        r = id_map.get(rid)
        if r is None:
            continue
        ok, err = store.removeReminder_commit_error_(r, False, None)
        if not ok:
            raise RuntimeError(f"removeReminder failed: {err}")

    new_ids: list[str] = []
    for c in batch.creates:
        r = EKReminder.reminderWithEventStore_(store)
        r.setCalendar_(cal)
        r.setTitle_(c["name"])
        r.setNotes_(c.get("body", ""))
        r.setPriority_(int(c.get("priority", 0)))
        if c.get("completed"):
            r.setCompleted_(True)
        ok, err = store.saveReminder_commit_error_(r, False, None)
        if not ok:
            raise RuntimeError(f"saveReminder failed: {err}")
        new_ids.append(str(r.calendarItemIdentifier()))

    ok, err = store.commit_(None)
    if not ok:
        raise RuntimeError(f"commit failed: {err}")
    return new_ids
