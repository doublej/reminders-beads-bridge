"""Thin wrapper around the `bd` CLI."""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Healthy `bd list --json --all` is ~1-2s even for the largest repo (~1400
# issues), but it is prone to episodic ~20x slowdowns that hit every project at
# once (2026-07-26: all four projects at 19-32s, the same call measured 68-90s;
# cleared on its own, trigger never identified — not load average or dolt server
# count, both of which stayed high afterwards). The old 30s cap had no headroom,
# so the largest project — and only it — crossed the line and failed every cycle
# while the rest merely ran slow. This bound is for riding out that episode, not
# for normal operation; a timeout at this value means something is actually wrong.
_TIMEOUT_S = float(os.getenv("RBRIDGE_BD_TIMEOUT_S", "180"))


@dataclass
class Issue:
    id: str
    title: str
    description: str
    status: str
    priority: int
    issue_type: str


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bd", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )


def list_issues(cwd: Path) -> list[Issue]:
    result = _run(["list", "--json", "--all"], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"bd list failed ({cwd}): {result.stderr.strip()}")
    try:
        raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"bd list returned invalid JSON ({cwd}): {e}") from e
    return [
        Issue(
            id=r["id"],
            title=r.get("title", ""),
            description=r.get("description", ""),
            status=r.get("status", ""),
            priority=r.get("priority", 0),
            issue_type=r.get("issue_type", "task"),
        )
        for r in raw
    ]


def close_issue(cwd: Path, issue_id: str, reason: str = "completed in Reminders") -> None:
    result = _run(["close", issue_id, "-m", reason], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"bd close {issue_id} failed: {result.stderr.strip()}")


def reopen_issue(cwd: Path, issue_id: str, reason: str = "unchecked in Reminders") -> None:
    result = _run(["reopen", issue_id, "-r", reason], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"bd reopen {issue_id} failed: {result.stderr.strip()}")


def create_issue(
    cwd: Path,
    title: str,
    description: str = "",
    priority: int = 2,
) -> Issue:
    args = ["create", title, "--json", "--priority", str(priority)]
    if description:
        args += ["--description", description]
    result = _run(args, cwd)
    if result.returncode != 0:
        raise RuntimeError(f"bd create failed ({cwd}): {result.stderr.strip()}")
    try:
        raw = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"bd create returned invalid JSON ({cwd}): {e}") from e
    data = raw.get("issue", raw) if isinstance(raw, dict) else {}
    if "id" not in data:
        raise RuntimeError(f"bd create returned no id: {raw!r}")
    return Issue(
        id=data["id"],
        title=data.get("title", title),
        description=data.get("description", description),
        status=data.get("status", "open"),
        priority=data.get("priority", priority),
        issue_type=data.get("issue_type", "task"),
    )


def doctor(cwd: Path) -> str:
    result = _run(["--version"], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"bd missing or broken: {result.stderr.strip()}")
    return result.stdout.strip()


# --- Dolt server lifecycle -------------------------------------------------
# Any `bd` call auto-starts a per-project `dolt sql-server` (~110MB RSS) and
# never stops it, so reconciling N projects on a timer pins N servers for the
# daemon's entire lifetime — measured 2026-09-08 at 7 servers / ~900MB for
# repos with no edits in weeks. The servers `setsid` away (PPID 1, own process
# group), so they can never be *in* our process group; we own them by ledger
# instead: skip `bd` while a project's beads data is unchanged (`journal_size`)
# and stop the server it left behind (`stop_server`).

_JOURNAL_GLOB = ".dolt/noms/" + "v" * 32


def journal_size(cwd: Path) -> int | None:
    """Total size of this project's Dolt write-ahead journals, or None if the
    project has none (fresh repo, unknown layout) and cannot be gated.

    This is the reconcile gate's change signal. Verified 2026-09-08 against a
    live server-mode repo: it moves on every mutation (create / close / reopen /
    note / delete) and stays put across read-only `bd list`, server start, and
    `bd dolt stop`. That blindness to server lifecycle is the load-bearing
    property — a signal that moved when the server did would make the reaper
    restart what it had just stopped, every cycle. (`manifest` and
    `.beads/last-touched` both fail one half of this and were rejected.)
    `bd gc`/`compact` rewrites the journal, which reads as a change: one
    redundant — and idempotent — reconcile, i.e. the safe direction.
    """
    total = 0
    found = False
    for p in (cwd / ".beads").rglob(_JOURNAL_GLOB):
        if "stats" in p.parts or "backup" in p.parts:
            continue  # the stats DB churns on read-only queries
        try:
            total += p.stat().st_size
        except OSError:
            continue
        found = True
    return total if found else None


def server_pid(cwd: Path) -> int | None:
    """PID of this project's running `dolt sql-server`, or None."""
    try:
        pid = int((cwd / ".beads" / "dolt-server.pid").read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def stop_server(cwd: Path) -> bool:
    """Stop this project's `dolt sql-server` if one is running; True if stopped.

    A memory reclaim, not a shutdown: `bd` restarts it transparently on the next
    command (measured ~0.7s cold vs ~0.2s warm).
    """
    if server_pid(cwd) is None:
        return False
    return _run(["dolt", "stop"], cwd).returncode == 0
