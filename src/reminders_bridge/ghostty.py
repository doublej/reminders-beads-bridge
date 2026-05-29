"""Discover live Claude Code sessions running inside Ghostty tabs.

A Ghostty surface is `Ghostty.app/.../ghostty → login → -zsh → claude`. We find
the ghostty root pid(s), then every interactive `claude` process whose ancestor
chain reaches one. "Interactive" = argv0 basename `claude` with a real tty —
this excludes the `claude daemon` and the detached `versions/<x>` helpers.
"""

import os
import subprocess
from dataclasses import dataclass

_GHOSTTY_MARK = "Ghostty.app/Contents/MacOS/ghostty"
_ENV = {**os.environ, "LANG": "C"}


@dataclass
class Proc:
    pid: int
    ppid: int
    tty: str
    command: str


@dataclass
class Tab:
    pid: int
    tty: str
    cwd: str
    project: str
    mode: str
    args: str


def _ps() -> list[Proc]:
    out = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,tty=,command="],
        capture_output=True, text=True, env=_ENV,
    ).stdout
    procs: list[Proc] = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        procs.append(Proc(int(parts[0]), int(parts[1]), parts[2], parts[3]))
    return procs


def _ghostty_pids(procs: list[Proc]) -> set[int]:
    return {p.pid for p in procs if _GHOSTTY_MARK in p.command}


def _has_ghostty_ancestor(pid: int, ppid_of: dict[int, int], roots: set[int]) -> bool:
    seen: set[int] = set()
    cur = pid
    while cur > 1 and cur not in seen:
        seen.add(cur)
        if cur in roots:
            return True
        cur = ppid_of.get(cur, 0)
    return False


def _is_claude(command: str) -> bool:
    tokens = command.split()
    if not tokens:
        return False
    if tokens[0].rsplit("/", 1)[-1] != "claude":
        return False
    return "daemon" not in tokens[1:2]


def _mode(args: str) -> str:
    if "--chrome" in args:
        return "chrome"
    if "--resume" in args:
        return "resume"
    return "cli"


def _resolve_cwd(pid: int) -> str:
    out = subprocess.run(
        ["lsof", "-p", str(pid), "-a", "-d", "cwd", "-F", "n"],
        capture_output=True, text=True, env=_ENV,
    ).stdout
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return ""


def discover() -> list[Tab]:
    procs = _ps()
    roots = _ghostty_pids(procs)
    if not roots:
        return []
    ppid_of = {p.pid: p.ppid for p in procs}
    tabs: list[Tab] = []
    for p in procs:
        if p.tty in ("??", "-") or not _is_claude(p.command):
            continue
        if not _has_ghostty_ancestor(p.pid, ppid_of, roots):
            continue
        cwd = _resolve_cwd(p.pid)
        tabs.append(Tab(
            pid=p.pid,
            tty=p.tty,
            cwd=cwd,
            project=cwd.rsplit("/", 1)[-1] if cwd else "-",
            mode=_mode(p.command),
            args=p.command,
        ))
    return sorted(tabs, key=lambda t: t.pid)
