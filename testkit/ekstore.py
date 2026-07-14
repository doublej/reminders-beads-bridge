"""EventKit-backed implementation of the five reminder_*_v0 tools.

Batched shapes (grouped creates, update/delete arrays) are accepted verbatim and
looped internally; store/calendar plumbing lives in ``ekbase``, field
conversions in ``ekconv``.
"""

from __future__ import annotations

from typing import Any

from EventKit import EKReminder  # type: ignore[import-not-found, import-untyped]

import ekbase
import ekconv


def list_lists(search_text: str | None = None) -> dict[str, Any]:
    store = ekbase.get_store()
    default_id = ekbase.default_id(store)
    out = []
    for cal in ekbase.calendars(store):
        title = str(cal.title())
        if search_text and search_text.lower() not in title.lower():
            continue
        items = ekbase.fetch(store, [cal])
        out.append(
            {
                "color": ekbase.hex_color(cal),
                "id": str(cal.calendarIdentifier()),
                "incomplete_count": sum(1 for r in items if not r.isCompleted()),
                "is_default": str(cal.calendarIdentifier()) == default_id,
                "item_count": len(items),
                "title": title,
            }
        )
    return {"lists": out, "status": "success"}


def search(
    searchText: str | None = None,
    listId: str | None = None,
    listName: str | None = None,
    status: str = "incomplete",
    dateFrom: str | None = None,
    dateTo: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    store = ekbase.get_store()
    want_completed = status == "completed"
    lo = ekconv.iso_to_nsdate(dateFrom).timeIntervalSince1970() if dateFrom else None
    hi = ekconv.iso_to_nsdate(dateTo).timeIntervalSince1970() if dateTo else None
    groups: list[dict[str, Any]] = []
    remaining = int(limit)
    for cal in ekbase.target_calendars(store, listId, listName):
        if remaining <= 0:
            break
        picked = []
        for r in ekbase.fetch(store, [cal]):
            if bool(r.isCompleted()) != want_completed:
                continue
            if searchText:
                hay = f"{r.title() or ''} {r.notes() or ''}".lower()
                if searchText.lower() not in hay:
                    continue
            if want_completed and (lo is not None or hi is not None):
                ref = r.completionDate()
                if ref is not None:
                    t = ref.timeIntervalSince1970()
                    if (lo is not None and t < lo) or (hi is not None and t > hi):
                        continue
            picked.append(r)
        picked = picked[:remaining]
        remaining -= len(picked)
        if picked:
            groups.append(
                {
                    "list_id": str(cal.calendarIdentifier()),
                    "list_name": str(cal.title()),
                    "reminders": [ekconv.serialize(r) for r in picked],
                }
            )
    return {"reminder_lists": groups, "status": "success"}


def create(reminder_lists: list[dict[str, Any]]) -> dict[str, Any]:
    store = ekbase.get_store()
    default_id = ekbase.default_id(store)
    out_groups = []
    for group in reminder_lists:
        cal = ekbase.calendar_for(store, group.get("listId"))
        items = []
        for i, item in enumerate(group.get("reminders", [])):
            r = EKReminder.reminderWithEventStore_(store)
            r.setCalendar_(cal)
            ekconv.apply_fields(r, item)
            ok, err = store.saveReminder_commit_error_(r, True, None)
            if not ok:
                raise RuntimeError(f"saveReminder failed: {err}")
            items.append(
                {
                    "id": str(r.calendarItemIdentifier()),
                    "index": i,
                    "title": str(r.title() or ""),
                }
            )
        out_groups.append(
            {
                "is_default_list": str(cal.calendarIdentifier()) == default_id,
                "list_id": str(cal.calendarIdentifier()),
                "list_name": str(cal.title()),
                "items": items,
            }
        )
    return {"reminder_lists": out_groups, "status": "success"}


def update(reminder_updates: list[dict[str, Any]]) -> dict[str, Any]:
    store = ekbase.get_store()
    by_id = ekbase.all_by_id(store)
    out = []
    for u in reminder_updates:
        r = by_id.get(u["id"])
        if r is None:
            out.append({"id": u["id"], "error": "not_found"})
            continue
        before = ekconv.serialize(r)
        ekconv.apply_fields(r, u)
        changed_list = False
        if u.get("listId"):
            r.setCalendar_(ekbase.calendar_for(store, u["listId"]))
            changed_list = True
        ok, err = store.saveReminder_commit_error_(r, True, None)
        if not ok:
            raise RuntimeError(f"saveReminder failed: {err}")
        after = ekconv.serialize(r)
        changed = sorted(
            k for k in set(before) | set(after) if before.get(k) != after.get(k)
        )
        if changed_list:
            changed.append("list_id")
        out.append(
            {"changed_fields": changed, "id": u["id"], "updated_reminder": after}
        )
    return {"reminder_updates": out, "status": "success"}


def delete(reminder_deletions: list[dict[str, Any]]) -> dict[str, Any]:
    store = ekbase.get_store()
    by_id = ekbase.all_by_id(store)
    out = []
    for d in reminder_deletions:
        r = by_id.get(d["id"])
        if r is None:
            out.append({"id": d["id"], "error": "not_found"})
            continue
        snap = ekconv.serialize(r)
        ok, err = store.removeReminder_commit_error_(r, True, None)
        if not ok:
            raise RuntimeError(f"removeReminder failed: {err}")
        out.append({"id": d["id"], "deleted_reminder": snap})
    return {"reminder_deletions": out, "status": "success"}
