"""`rbridge prime` — emit the voice-takeout playbook + live environment.

The playbook text lives in `primer.md` (single source of truth, ships in the
wheel). This module reads it, appends a detected-environment block so the agent
knows the cwd that would become the nav root and which exchanges are open, and
optionally emits a structured JSON contract for machine ingest. Markdown is the
default — the consumer is the agent's reasoning, not a parser (cf.
agent-friendly-cli `prime` convention).
"""

import json
import os
import sys
from importlib import resources

from . import mailbox as mailbox_module
from . import navigation as navigation_module

RESPONSE_KINDS = ["decision", "note", "question", "deferred", "done", "free"]
NAV_VERBS = {
    "fetch: <path> [page N]": "file contents → rewritten to `file:`",
    "grep: <term>": "search the tree → rewritten to `results:`",
    "tree: [subdir]": "directory listing → rewritten to `listing:`",
}


def run(args: list[str]) -> None:
    if "--json" in args:
        json.dump(_contract(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_markdown())


def _primer_text() -> str:
    return (
        resources.files("reminders_bridge")
        .joinpath("primer.md")
        .read_text(encoding="utf-8")
    )


def _detected() -> dict:
    boxes = mailbox_module.list_active()
    return {
        "cwd": os.getcwd(),
        "nav_enabled": navigation_module.sandbox.nav_enabled(),
        "active_mailboxes": [
            {"slug": mb.slug, "kind": mb.kind, "root": mb.source_cwd or None}
            for mb in boxes
        ],
    }


def _detected_block(d: dict) -> str:
    cwd = d["cwd"]
    nav = "ENABLED" if d["nav_enabled"] else "DISABLED (RBRIDGE_VOICE_NAV=0)"
    lines = [
        "## Detected (live)",
        "",
        f"- cwd (becomes the nav root if you open here): `{cwd}`",
        f"- file-nav globally: {nav}",
    ]
    boxes = d["active_mailboxes"]
    if boxes:
        lines.append(f"- {len(boxes)} open exchange(s):")
        for mb in boxes:
            lines.append(
                f"  - `{mb['slug']}` ({mb['kind']}) root=`{mb['root'] or '—'}`"
            )
    else:
        lines.append("- no open exchanges")
    nxt = (
        "rbridge mailbox open --slug <slug> --kind REMINDERS --brief - "
        f'--cwd "{cwd}" <<< "$(cat <brief>)"'
    )
    lines += ["", f"Next: gather context, compose a brief, then `{nxt}`", ""]
    return "\n".join(lines)


def _markdown() -> str:
    return _primer_text().rstrip() + "\n\n---\n\n" + _detected_block(_detected())


def _contract() -> dict:
    return {
        "name": "rbridge",
        "purpose": "Voice exchange handoff: compose a brief, open a Reminders "
        "mailbox, drain responses.",
        "commands": {
            "prime": "this primer; --json for the contract",
            "mailbox open": "--slug --kind {REMINDERS,CLAUDE_VOICE} --brief - --cwd PATH",
            "mailbox read": "--slug; drain responses as JSON",
            "mailbox close": "--slug; tear down",
            "mailbox refresh": "--slug; re-up reminders, keep brief",
            "mailbox list": "enumerate active mailboxes",
        },
        "kinds": {
            "CLAUDE_VOICE": "TTS prose, pbcopy, one-way, no CLI call",
            "REMINDERS": "writeback via Reminders list, drained with `mailbox read`",
        },
        "shapes": {
            "decision": "converge on a few decisions; 250-500 words",
            "reference": "carry a whole corpus; no length cap; per-item facts",
        },
        "response_kinds": RESPONSE_KINDS,
        "nav_verbs": NAV_VERBS,
        "list_name": "_rb_voice_<slug>",
        "brief_path": "~/.claude/voice-takeouts/<YYYYMMDD-HHMM>-<slug>.md",
        "exit_codes": {"1": "empty brief / bad slug", "2": "Reminders unavailable"},
        "detected": _detected(),
    }
