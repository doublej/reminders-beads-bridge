"""Thin wrapper around the `bd` CLI."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


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
        timeout=30,
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
