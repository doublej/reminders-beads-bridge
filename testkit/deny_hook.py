#!/usr/bin/env python3
"""PreToolUse hook: allow ONLY the replica's reminder tools, deny all else.

The isolated agent must have exactly the voice surface and nothing to fall back
on. --strict-mcp-config + --disallowedTools already narrow the toolset; this
hook is the hard backstop so any tool that slips through (a future built-in, a
name we didn't disallow) is denied rather than silently used. Allowed names are
the MCP-namespaced tools from our "reminders" server: mcp__reminders__*.
"""

import json
import os
import sys

ALLOW_PREFIX = "mcp__reminders__"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    name = data.get("tool_name", "")
    allow = name.startswith(ALLOW_PREFIX)
    log = os.environ.get("RBRIDGE_HOOK_LOG")
    if log:
        with open(log, "a") as f:
            f.write(f"{'ALLOW' if allow else 'DENY '} {name}\n")
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allow else "deny",
            "permissionDecisionReason": (
                "reminders replica tool"
                if allow
                else f"{name!r} is outside the voice surface (reminder tools only)"
            ),
        }
    }
    print(json.dumps(decision))
    sys.exit(0)


if __name__ == "__main__":
    main()
