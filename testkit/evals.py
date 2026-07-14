#!/usr/bin/env python3
"""Starter evals for the voice-surface replica agent.

Each eval drives the isolated agent (run.run) with a prompt and asserts on the
captured tool calls + the spoken utterance. Mutating evals use a uniquely-named
throwaway list and delete it in teardown, so a run leaves Reminders as it found
it. Extend this list with bridge-coupling cases (see README → "Daemon-coupling
evals") once you have a dedicated test beads project.

    uv run --extra testkit python testkit/evals.py          # all
    uv run --extra testkit python testkit/evals.py isolation # one
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from reminders_bridge import reminders as rem  # type: ignore[import-untyped]

import run

_BANNED_OPENERS = (
    "sure", "got it", "of course", "perfect", "i'll", "let me", "happy to",
    "i have", "i've", "here", "okay", "great",
)


@dataclass
class Eval:
    name: str
    prompt: str
    check: Callable[[dict[str, Any]], str | None]  # return None=pass, str=reason
    setup: Callable[[], None] = lambda: None
    teardown: Callable[[], None] = lambda: None
    tags: list[str] = field(default_factory=list)


def _only_reminder_tools(r: dict[str, Any]) -> str | None:
    stray = [t["name"] for t in r["tool_calls"] if not t["name"].startswith("mcp__reminders__")]
    return f"used non-reminder tools: {stray}" if stray else None


def _creates(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for t in r["tool_calls"]:
        if t["name"].endswith("reminder_create_v0"):
            for g in (t["input"] or {}).get("reminderLists", []):
                out.extend(g.get("reminders", []))
    return out


def _one_per_item(r: dict[str, Any]) -> str | None:
    items = _creates(r)
    if len(items) < 3:
        return f"expected ≥3 separate reminders, got {len(items)}: {[i.get('title') for i in items]}"
    bulleted = [i for i in items if "\n" in (i.get("notes") or "")]
    if bulleted:
        return "packed items into a bulleted note instead of one reminder each"
    return _only_reminder_tools(r)


def _speakable(r: dict[str, Any]) -> str | None:
    u = (r["utterance"] or "").strip()
    if not u:
        return "no utterance"
    if len(u) > 240:
        return f"utterance too long to speak ({len(u)} chars)"
    low = u.lower()
    hit = next((o for o in _BANNED_OPENERS if low.startswith(o)), None)
    if hit:
        return f"opens with filler {hit!r} (bad for a spoken receipt)"
    return _only_reminder_tools(r)


_LIST = "RbTestkitEval"


def _mk_list() -> None:
    rem.create_list(_LIST)


def _rm_list() -> None:
    rem.delete_list(_LIST)


EVALS = [
    Eval(
        name="isolation",
        prompt="How many reminder lists do I have? Just the number.",
        check=_only_reminder_tools,
        tags=["read"],
    ),
    Eval(
        name="one_per_item",
        prompt=f"Add milk, eggs and bread to my {_LIST} list.",
        check=_one_per_item,
        setup=_mk_list,
        teardown=_rm_list,
        tags=["write"],
    ),
    Eval(
        name="speakable_receipt",
        prompt=f"Add 'buy stamps' to my {_LIST} list.",
        check=_speakable,
        setup=_mk_list,
        teardown=_rm_list,
        tags=["write"],
    ),
]


def run_one(ev: Eval) -> bool:
    ev.setup()
    try:
        result = run.run(ev.prompt)
        reason = None if result.get("is_error") is False else (
            f"agent errored: {result.get('stderr', '')[:200]}"
        )
        reason = reason or ev.check(result)
    finally:
        ev.teardown()
    mark = "PASS" if reason is None else "FAIL"
    print(f"[{mark}] {ev.name}")
    if reason:
        print(f"       {reason}")
    else:
        print(f"       tools={[t['name'].split('__')[-1] for t in result['tool_calls']]}")
        print(f"       said: {(result['utterance'] or '')[:100]!r}")
    return reason is None


def main() -> None:
    wanted = sys.argv[1:]
    evals = [e for e in EVALS if not wanted or e.name in wanted]
    if not evals:
        print(f"no eval matches {wanted}; have: {[e.name for e in EVALS]}")
        sys.exit(2)
    passed = sum(run_one(e) for e in evals)
    print(f"\n{passed}/{len(evals)} passed")
    sys.exit(0 if passed == len(evals) else 1)


if __name__ == "__main__":
    main()
