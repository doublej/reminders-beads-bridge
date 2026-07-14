#!/usr/bin/env python3
"""Drive an isolated Claude Code agent that has ONLY the voice reminder surface.

The agent runs with a clean CLAUDE_CONFIG_DIR (no global/project CLAUDE.md), a
strict MCP config exposing just our replica server, a built-in denylist, and a
PreToolUse hook that hard-blocks anything outside mcp__reminders__*. So it can
reach for nothing but the six replica tools — no Bash, Read, web, or calendar to
paper over gaps, exactly like the phone.

The agent's text output is what a voice user would HEAR, so it's surfaced as the
first-class ``utterance``; tool calls are captured separately for assertions.

    python run.py "add milk, eggs and bread to my groceries"
    python run.py --json "close bd-18" | jq .tool_calls
    from run import run; r = run("what's open in reminders-bridge?")
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

TESTKIT = Path(__file__).resolve().parent
REPO = TESTKIT.parent
HOME = Path(os.environ.get("RBRIDGE_TESTKIT_HOME", Path.home() / ".rbridge-testkit"))

# Built-ins hidden from the model (the hook is the hard backstop for the rest).
DISALLOWED = [
    "Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "Glob", "Grep", "LS", "WebFetch", "WebSearch", "Task",
    "TodoWrite", "ExitPlanMode", "SlashCommand",
]
ALLOWED = [f"mcp__reminders__{n}" for n in (
    "reminder_list_search_v0", "reminder_search_v0", "reminder_create_v0",
    "reminder_update_v0", "reminder_delete_v0", "user_time_v0",
)]


def provision() -> tuple[Path, Path]:
    """Write the isolated config dir + agent cwd (idempotent, absolute paths)."""
    cfg, agent = HOME / "config", HOME / "agent"
    cfg.mkdir(parents=True, exist_ok=True)
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "reminders.mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "reminders": {
                        "command": "uv",
                        "args": [
                            "run", "--project", str(REPO), "--extra", "testkit",
                            "python", str(TESTKIT / "mcp_server.py"),
                        ],
                    }
                }
            },
            indent=2,
        )
    )
    (agent / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"python3 {TESTKIT / 'deny_hook.py'}",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
    )
    return cfg, agent


def _parse(stdout: str, stderr: str, code: int) -> dict[str, Any]:
    events, utterances, tool_calls, result = [], [], [], None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(ev)
        if ev.get("type") == "assistant":
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip():
                    utterances.append(c["text"].strip())
                elif c.get("type") == "tool_use":
                    tool_calls.append({"name": c.get("name"), "input": c.get("input")})
        elif ev.get("type") == "result":
            result = ev
    result = result or {}
    return {
        "utterance": result.get("result") or (utterances[-1] if utterances else ""),
        "utterances": utterances,
        "tool_calls": tool_calls,
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "is_error": bool(result.get("is_error", code != 0)),
        "returncode": code,
        "stderr": stderr,
        "raw_events": events,
    }


def run(prompt: str, model: str | None = None, timeout: int = 180) -> dict[str, Any]:
    cfg, agent = provision()
    cmd = [
        "claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
        "--mcp-config", str(agent / "reminders.mcp.json"), "--strict-mcp-config",
        "--settings", str(agent / "settings.json"),
        "--allowedTools", *ALLOWED,
        "--disallowedTools", *DISALLOWED,
    ]
    if model:
        cmd += ["--model", model]
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(cfg))
    try:
        proc = subprocess.run(
            cmd, cwd=str(agent), env=env, capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        serr = e.stderr or ""
        if isinstance(serr, bytes):
            serr = serr.decode(errors="replace")
        return {
            "utterance": "", "utterances": [], "tool_calls": [], "is_error": True,
            "returncode": -1, "stderr": f"timeout after {timeout}s\n{serr}",
            "raw_events": [],
        }
    return _parse(proc.stdout, proc.stderr, proc.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the isolated voice-surface agent.")
    ap.add_argument("prompt", nargs="?", help="prompt to send (default: stdin)")
    ap.add_argument("--model", help="model override (e.g. claude-sonnet-5)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--json", action="store_true", help="emit the structured result")
    ap.add_argument("--raw", action="store_true", help="keep raw_events in --json")
    args = ap.parse_args()
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        ap.error("no prompt given")
    r = run(prompt, args.model, args.timeout)
    if args.json:
        if not args.raw:
            r.pop("raw_events", None)
        print(json.dumps(r, indent=2, default=str))
        return
    print("── tool calls ──")
    for tc in r["tool_calls"]:
        print(f"  {tc['name']}  {json.dumps(tc['input'], default=str)[:160]}")
    if not r["tool_calls"]:
        print("  (none)")
    print("\n── utterance (spoken) ──")
    print(r["utterance"] or "(silence)")
    if r["is_error"]:
        print(f"\n[error rc={r['returncode']}]\n{r['stderr'][:800]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
