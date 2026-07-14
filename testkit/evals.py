#!/usr/bin/env python3
"""Executable voice scenarios, driven against the real agent (Sonnet by default).

Each case runs the isolated agent on a phone-style prompt (see scenarios.md) and
verifies the *effect* by reading the real Reminders store back — not just the
tool calls. Mutating cases use one throwaway list, wiped in setup and teardown,
so a run leaves Reminders as it found it.

    uv run --extra testkit python testkit/evals.py                 # all
    uv run --extra testkit python testkit/evals.py close reprio    # subset
    RBRIDGE_AGENT_MODEL=opus uv run --extra testkit python testkit/evals.py
"""

from __future__ import annotations

from reminders_bridge import reminders as rem  # type: ignore[import-untyped]

import ekstore
from evalkit import (
    Eval,
    all_of,
    creates,
    main,
    only_reminder_tools,
    read_directive,
    speakable,
    used,
)

LIST = "RbTestkitEval"


# ── throwaway-list helpers ──────────────────────────────────────────────────
def fresh() -> None:
    rem.delete_list(LIST)
    rem.create_list(LIST)


def wipe() -> None:
    rem.delete_list(LIST)


def seed(title: str, notes: str = "") -> None:
    fresh()
    lid = next(x["id"] for x in ekstore.list_lists(LIST)["lists"] if x["title"] == LIST)
    ekstore.create([{"listId": lid, "reminders": [{"title": title, "notes": notes}]}])


def _items(status: str = "incomplete") -> list[dict]:
    groups = ekstore.search(listName=LIST, status=status)["reminder_lists"]
    return [r for g in groups for r in g["reminders"]]


def _find(sub: str, status: str = "incomplete") -> dict | None:
    return next((r for r in _items(status) if sub.lower() in r["title"].lower()), None)


# ── effect checks (read the store back) ─────────────────────────────────────
def one_per_item(r):
    items = creates(r)
    if len(items) < 3:
        return f"expected ≥3 reminders, got {[i.get('title') for i in items]}"
    if any("\n" in (i.get("notes") or "") for i in items):
        return "packed items into a bulleted note instead of one each"
    return None if len(_items()) >= 3 else "items did not land in the list"


def single_landed(sub):
    def check(r):
        items = _items()
        if len(items) != 1:
            return f"expected exactly 1 reminder, got {[i['title'] for i in items]}"
        return None if sub in items[0]["title"].lower() else f"title missing {sub!r}"
    return check


def now_high(sub):
    def check(r):
        it = _find(sub)
        if it is None:
            return f"{sub!r} not found (did it get renamed/moved?)"
        return None if it["priority"] == "high" else f"priority is {it['priority']}"
    return check


def now_closed(sub):
    def check(r):
        if _find(sub, status="incomplete") is not None:
            return f"{sub!r} is still incomplete"
        return None if _find(sub, status="completed") else f"{sub!r} vanished"
    return check


def note_added_intact(sub, needle):
    def check(r):
        it = _find(sub)
        if it is None:
            return f"{sub!r} not found"
        notes = it.get("notes", "")
        if needle.lower() not in notes.lower():
            return f"note {needle!r} not written"
        if "<bb:meta>" not in notes or "<bb:desc>" not in notes:
            return "clobbered <bb:meta>/<bb:desc> (tamper) instead of editing notes"
        return None
    return check


_TICKET_BODY = (
    "<bb:meta>[bug · p1 · open]</bb:meta>\n\n"
    "<bb:desc>\nFilters reset on tab switch.\n</bb:desc>\n\n"
    "<bb:notes>\n</bb:notes>\n"
)


EVALS = [
    # ── read (safe; assert behaviour, not live content) ──
    Eval(
        name="list_count",
        prompt="How many reminder lists do I have? Just the number.",
        check=all_of(only_reminder_tools, lambda r: used(r, "reminder_list_search_v0")),
        tags=["read"],
    ),
    Eval(
        name="whats_open",
        prompt="What's open across my projects? Keep it short.",
        check=all_of(only_reminder_tools, read_directive, speakable,
                     lambda r: used(r, "reminder_search_v0")),
        tags=["read"],
    ),
    # ── write (throwaway list; assert the effect) ──
    Eval(
        name="dump_three",
        prompt=f"Add milk, eggs and bread to my {LIST} list.",
        check=all_of(only_reminder_tools, one_per_item),
        setup=fresh, teardown=wipe, tags=["write"],
    ),
    Eval(
        name="capture_single",
        prompt=f"Add 'renew the domain' to my {LIST} list.",
        check=all_of(only_reminder_tools, single_landed("domain")),
        setup=fresh, teardown=wipe, tags=["write"],
    ),
    Eval(
        name="reprioritize",
        prompt=f"In my {LIST} list, bump the sleep-wake crash to high priority.",
        check=all_of(only_reminder_tools, lambda r: used(r, "reminder_update_v0"),
                     now_high("sleep-wake crash")),
        setup=lambda: seed("bd-77: sleep-wake crash"), teardown=wipe, tags=["write"],
    ),
    Eval(
        name="close",
        prompt=f"Close the csv export bug in my {LIST} list.",
        check=all_of(only_reminder_tools, speakable,
                     lambda r: used(r, "reminder_update_v0"), now_closed("csv export")),
        setup=lambda: seed("bd-88: csv export bug"), teardown=wipe, tags=["write"],
    ),
    Eval(
        name="add_note_preserve",
        prompt=f"On the filters reset ticket in {LIST}, note that it only happens on Safari.",
        check=all_of(only_reminder_tools,
                     note_added_intact("filters reset", "safari")),
        setup=lambda: seed("bd-99: filters reset", _TICKET_BODY),
        teardown=wipe, tags=["write"],
    ),
]


if __name__ == "__main__":
    main(EVALS)
