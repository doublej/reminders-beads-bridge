"""Field conversions between the reminder_*_v0 wire shapes and EventKit.

Inputs are camelCase (as the live tools accept); serialized reminders are
snake_case (as the live tools return), with optional fields omitted when unset
— matching the probed response shapes. Priority mirrors the daemon's own
bead→EK map in ``link.py`` (0=none, 1-4=high, 5=medium, 6-9=low).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from EventKit import (  # type: ignore[import-not-found, import-untyped]
    EKAlarm,
    EKRecurrenceEnd,
    EKRecurrenceRule,
    EKReminder,
)
from Foundation import (  # type: ignore[import-not-found, import-untyped]
    NSCalendar,
    NSDate,
    NSDateComponents,
    NSURL,
)

# NSDateComponentUndefined — a large sentinel EventKit returns for unset fields.
_UNDEF = 9223372036854775807
_ENUM_TO_EK = {"none": 0, "low": 9, "medium": 5, "high": 1}
_FREQ = {"daily": 0, "weekly": 1, "monthly": 2, "yearly": 3}
_UNIT_YMD = 4 | 8 | 16  # NSCalendarUnitYear|Month|Day
_UNIT_YMDHM = _UNIT_YMD | 32 | 64  # + Hour|Minute


# ── priority ──────────────────────────────────────────────────────────────
def ek_to_enum(p: int) -> str:
    if p == 0:
        return "none"
    if 1 <= p <= 4:
        return "high"
    if p == 5:
        return "medium"
    return "low"


def enum_to_ek(name: str) -> int:
    return _ENUM_TO_EK.get(name, 0)


# ── dates ─────────────────────────────────────────────────────────────────
def iso_to_nsdate(iso: str) -> NSDate:
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.astimezone()
    return NSDate.dateWithTimeIntervalSince1970_(d.timestamp())


def nsdate_to_iso(d: NSDate) -> str:
    return (
        dt.datetime.fromtimestamp(d.timeIntervalSince1970())
        .astimezone()
        .isoformat()
    )


def iso_to_due(iso: str, includes_time: bool) -> NSDateComponents:
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.tzinfo is not None:
        d = d.astimezone()
    cal = NSCalendar.currentCalendar()
    units = _UNIT_YMDHM if includes_time else _UNIT_YMD
    return cal.components_fromDate_(units, iso_to_nsdate(d.isoformat()))


def due_to_iso(comps: NSDateComponents) -> tuple[str | None, bool]:
    y, m, day = comps.year(), comps.month(), comps.day()
    if _UNDEF in (y, m, day):
        return None, False
    hour, minute = comps.hour(), comps.minute()
    if hour == _UNDEF or minute == _UNDEF:
        return f"{y:04d}-{m:02d}-{day:02d}", False
    return f"{y:04d}-{m:02d}-{day:02d}T{hour:02d}:{minute:02d}:00", True


# ── alarms / recurrence (best-effort; never raise) ──────────────────────────
def build_alarm(a: dict[str, Any]) -> EKAlarm | None:
    try:
        if a.get("type") == "absolute" and a.get("date"):
            return EKAlarm.alarmWithAbsoluteDate_(iso_to_nsdate(a["date"]))
        if a.get("type") == "relative" and a.get("secondsBefore") is not None:
            return EKAlarm.alarmWithRelativeOffset_(-float(a["secondsBefore"]))
    except Exception:
        return None
    return None


def build_recurrence(r: dict[str, Any]) -> EKRecurrenceRule | None:
    try:
        freq = _FREQ.get(str(r.get("frequency", "")).lower())
        if freq is None:
            return None
        interval = max(1, int(r.get("interval", 1)))
        end = None
        e = r.get("end") or {}
        if e.get("type") == "count" and e.get("count"):
            end = EKRecurrenceEnd.recurrenceEndWithOccurrenceCount_(int(e["count"]))
        elif e.get("type") == "until" and e.get("until"):
            end = EKRecurrenceEnd.recurrenceEndWithEndDate_(iso_to_nsdate(e["until"]))
        return EKRecurrenceRule.alloc().initRecurrenceWithFrequency_interval_end_(
            freq, interval, end
        )
    except Exception:
        return None


# ── reminder ↔ dict ─────────────────────────────────────────────────────────
def serialize(r: EKReminder) -> dict[str, Any]:
    """EK reminder → snake_case dict, omitting optional fields that are unset."""
    out: dict[str, Any] = {
        "id": str(r.calendarItemIdentifier()),
        "title": str(r.title() or ""),
    }
    notes = str(r.notes() or "")
    if notes:
        out["notes"] = notes
    out["priority"] = ek_to_enum(int(r.priority()))
    due = r.dueDateComponents()
    if due is not None:
        iso, incl = due_to_iso(due)
        if iso:
            out["due_date"] = iso
            out["due_date_includes_time"] = incl
    url = r.URL()
    if url is not None:
        out["url"] = str(url.absoluteString())
    comp = r.completionDate()
    if comp is not None:
        out["completion_date"] = nsdate_to_iso(comp)
    return out


def apply_fields(r: EKReminder, f: dict[str, Any]) -> None:
    """Write camelCase input fields onto an EK reminder (partial)."""
    if "title" in f:
        r.setTitle_(f["title"])
    if "notes" in f:
        r.setNotes_(f.get("notes") or "")
    if f.get("url"):
        r.setURL_(NSURL.URLWithString_(f["url"]))
    if "priority" in f and f["priority"] is not None:
        r.setPriority_(enum_to_ek(f["priority"]))
    if "dueDate" in f:
        if f["dueDate"] is None:
            r.setDueDateComponents_(None)
        else:
            r.setDueDateComponents_(
                iso_to_due(f["dueDate"], bool(f.get("dueDateIncludesTime", False)))
            )
    if "completionDate" in f:
        cd = f["completionDate"]
        if cd is None:
            r.setCompleted_(False)
        else:
            r.setCompletionDate_(iso_to_nsdate(cd))
    for a in f.get("alarms") or []:
        al = build_alarm(a)
        if al is not None:
            r.addAlarm_(al)
    if f.get("recurrence"):
        rule = build_recurrence(f["recurrence"])
        if rule is not None:
            r.addRecurrenceRule_(rule)
