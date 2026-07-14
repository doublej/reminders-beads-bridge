"""Eval framework for the voice-surface agent: dataclass, shared checks, runner.

The agent under test defaults to Sonnet (override with RBRIDGE_AGENT_MODEL).
A check returns None to pass or a short reason string to fail; compose with
``all_of``. Cases live in evals.py.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import run

MODEL = os.environ.get("RBRIDGE_AGENT_MODEL", "sonnet")
# The phone always has the !_rb_readme directive; the suite mirrors that by
# default. Set RBRIDGE_DIRECTIVE=0 to test the bare tool surface instead.
DIRECTIVE = os.environ.get("RBRIDGE_DIRECTIVE", "1") not in ("0", "false", "")

Check = Callable[[dict[str, Any]], "str | None"]

_BANNED_OPENERS = (
    "sure", "got it", "of course", "perfect", "i'll", "let me", "happy to",
    "i have", "i've", "here", "okay", "great",
)


@dataclass
class Eval:
    name: str
    prompt: str
    check: Check
    setup: Callable[[], None] = lambda: None
    teardown: Callable[[], None] = lambda: None
    tags: list[str] = field(default_factory=list)
    directive: bool = DIRECTIVE  # give this case the phone's standing directive


def all_of(*checks: Check) -> Check:
    def run_all(r: dict[str, Any]) -> str | None:
        for c in checks:
            reason = c(r)
            if reason:
                return reason
        return None

    return run_all


def only_reminder_tools(r: dict[str, Any]) -> str | None:
    stray = [
        t["name"] for t in r["tool_calls"]
        if not t["name"].startswith("mcp__reminders__")
    ]
    return f"used non-reminder tools: {stray}" if stray else None


def speakable(r: dict[str, Any]) -> str | None:
    u = (r["utterance"] or "").strip()
    if not u:
        return "no utterance"
    if len(u) > 240:
        return f"utterance too long to speak ({len(u)} chars)"
    low = u.lower()
    hit = next((o for o in _BANNED_OPENERS if low.startswith(o)), None)
    return f"opens with filler {hit!r}" if hit else None


def used(r: dict[str, Any], suffix: str) -> str | None:
    names = [t["name"] for t in r["tool_calls"]]
    ok = any(n.endswith(suffix) for n in names)
    return None if ok else f"expected a {suffix} call; got {names}"


def read_directive(r: dict[str, Any]) -> str | None:
    """Parity: the agent fetched the live !_rb_readme directive itself."""
    for t in r["tool_calls"]:
        inp = t.get("input") or {}
        blob = f"{inp.get('listName', '')} {inp.get('searchText', '')}".lower()
        if t["name"].endswith(("reminder_search_v0", "reminder_list_search_v0")) and "readme" in blob:
            return None
    return "did not read the !_rb_readme directive (briefing missed)"


def creates(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for t in r["tool_calls"]:
        if t["name"].endswith("reminder_create_v0"):
            for g in (t["input"] or {}).get("reminderLists", []):
                out.extend(g.get("reminders", []))
    return out


def run_one(ev: Eval) -> bool:
    ev.setup()
    result: dict[str, Any] = {}
    try:
        result = run.run(ev.prompt, model=MODEL, directive=ev.directive)
        reason = (
            None if result.get("is_error") is False
            else f"agent errored: {result.get('stderr', '')[:200]}"
        )
        reason = reason or ev.check(result)
    finally:
        ev.teardown()
    mark = "PASS" if reason is None else "FAIL"
    print(f"[{mark}] {ev.name}")
    if reason:
        print(f"       {reason}")
    else:
        tools = [t["name"].split("__")[-1] for t in result["tool_calls"]]
        print(f"       tools={tools}  said={(result['utterance'] or '')[:80]!r}")
    return reason is None


def main(cases: list[Eval]) -> None:
    wanted = sys.argv[1:]
    evals = [e for e in cases if not wanted or e.name in wanted]
    if not evals:
        print(f"no eval matches {wanted}; have: {[e.name for e in cases]}")
        sys.exit(2)
    print(f"model: {MODEL}\n")
    passed = sum(run_one(e) for e in evals)
    print(f"\n{passed}/{len(evals)} passed")
    sys.exit(0 if passed == len(evals) else 1)
