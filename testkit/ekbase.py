"""EventKit store/calendar helpers shared by the reminder tool ops.

Reuses the daemon's authed EKEventStore (``reminders_bridge.reminders``) so the
replica hits the same Reminders database the daemon and the real voice agent do.
"""

from __future__ import annotations

from typing import Any

from EventKit import (  # type: ignore[import-not-found, import-untyped]
    EKEntityTypeReminder,
    EKReminder,
)
from Foundation import (  # type: ignore[import-not-found, import-untyped]
    NSDate,
    NSRunLoop,
)
from reminders_bridge import reminders as rem  # type: ignore[import-untyped]

get_store = rem.get_store


def spin(cond) -> None:
    loop = NSRunLoop.currentRunLoop()
    while cond():
        loop.runMode_beforeDate_(
            "NSDefaultRunLoopMode", NSDate.dateWithTimeIntervalSinceNow_(0.25)
        )


def fetch(store, cals) -> list[EKReminder]:
    predicate = store.predicateForRemindersInCalendars_(cals)
    state: dict[str, Any] = {"done": False, "items": []}

    def cb(items):
        state["items"] = list(items or [])
        state["done"] = True

    store.fetchRemindersMatchingPredicate_completion_(predicate, cb)
    spin(lambda: not state["done"])
    return state["items"]


def calendars(store) -> list:
    return list(store.calendarsForEntityType_(EKEntityTypeReminder))


def default_id(store) -> str | None:
    d = store.defaultCalendarForNewReminders()
    return str(d.calendarIdentifier()) if d else None


def calendar_for(store, list_id: str | None):
    """Empty/None list_id → default list; otherwise resolve by identifier."""
    if not list_id:
        d = store.defaultCalendarForNewReminders()
        if d is None:
            raise RuntimeError("no default Reminders list")
        return d
    for cal in calendars(store):
        if str(cal.calendarIdentifier()) == list_id:
            return cal
    raise RuntimeError(f"list not found: {list_id}")


def target_calendars(store, list_id: str | None, list_name: str | None) -> list:
    if list_id:
        return [calendar_for(store, list_id)]
    if list_name:
        return [c for c in calendars(store) if str(c.title()) == list_name]
    return calendars(store)


def hex_color(cal) -> str:
    try:
        c = cal.color()
        r, g, b = (
            int(round(c.redComponent() * 255)),
            int(round(c.greenComponent() * 255)),
            int(round(c.blueComponent() * 255)),
        )
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#000000"


def all_by_id(store) -> dict[str, EKReminder]:
    return {
        str(r.calendarItemIdentifier()): r for r in fetch(store, calendars(store))
    }
