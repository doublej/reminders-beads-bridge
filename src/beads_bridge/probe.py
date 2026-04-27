"""Diagnostic: enumerate EKReminder fields to see what round-trips.

Writes one reminder into a disposable list, sets every field we might use,
reads it back, prints what survived, then deletes the list.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from EventKit import (  # type: ignore[import-not-found]
    EKAlarm,
    EKEntityTypeReminder,
    EKReminder,
)
from Foundation import NSDate, NSDateComponents, NSURL  # type: ignore[import-not-found]

from . import reminders as rm

_LIST = "Beads: __probe__"
_READ_FIELDS = [
    "title",
    "notes",
    "URL",
    "location",
    "priority",
    "dueDateComponents",
    "startDateComponents",
    "completionDate",
    "alarms",
    "hasAlarms",
    "hasRecurrenceRules",
    "hasNotes",
    "creationDate",
    "lastModifiedDate",
    "calendarItemExternalIdentifier",
    "timeZone",
]


def _components(dt: datetime) -> NSDateComponents:
    c = NSDateComponents.alloc().init()
    c.setYear_(dt.year)
    c.setMonth_(dt.month)
    c.setDay_(dt.day)
    c.setHour_(dt.hour)
    c.setMinute_(dt.minute)
    return c


def _write(store: Any) -> str:
    rm.create_list(_LIST)
    cal = rm._find_calendar(store, _LIST)
    r = EKReminder.reminderWithEventStore_(store)
    r.setCalendar_(cal)
    r.setTitle_("bd-probe: test #bd-42 #ticket 🧪")
    r.setNotes_("line 1\n#tag-in-body\nhttps://example.com/inline")
    r.setPriority_(1)
    r.setURL_(NSURL.URLWithString_("https://beads.local/issue/bd-42"))
    r.setLocation_("Zwolle NL")
    r.setDueDateComponents_(_components(datetime.now(timezone.utc) + timedelta(days=1)))
    r.setStartDateComponents_(_components(datetime.now(timezone.utc) + timedelta(hours=3)))
    r.addAlarm_(EKAlarm.alarmWithAbsoluteDate_(NSDate.dateWithTimeIntervalSinceNow_(3600)))
    ok, err = store.saveReminder_commit_error_(r, True, None)
    if not ok:
        raise RuntimeError(f"save failed: {err}")
    return str(r.calendarItemIdentifier())


def _field(r: Any, selector: str) -> str:
    try:
        val = getattr(r, selector)()
    except Exception as e:
        return f"<err {e}>"
    return repr(val)


def _read(store: Any, rid: str) -> None:
    cal = rm._find_calendar(store, _LIST)
    items = rm._fetch(store, cal)
    r = next((x for x in items if str(x.calendarItemIdentifier()) == rid), None)
    if r is None:
        print("  (reminder missing after save)")
        return
    for sel in _READ_FIELDS:
        print(f"  {sel:32s} = {_field(r, sel)}")
    tag_like = sorted(
        s for s in dir(r)
        if ("tag" in s.lower() or "hashtag" in s.lower() or "label" in s.lower())
        and not s.startswith("_")
    )
    print(f"\n  selectors containing tag/hashtag/label: {tag_like or '(none)'}")


def run() -> None:
    store = rm.get_store()
    try:
        rid = _write(store)
        print(f"Probe saved {rid} in {_LIST!r}. Readback:\n")
        _read(store, rid)
    finally:
        if rm.delete_list(_LIST):
            print(f"\nProbe list {_LIST!r} deleted.")
