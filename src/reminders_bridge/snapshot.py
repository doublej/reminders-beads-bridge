"""Read-only facade: assemble bridge state for the dashboard, per view.

Reads are file/subprocess based where possible (registry, `state.json`,
`bd list`, the activity log, `ps`-based tab discovery, mailbox state files) and
read-only EventKit where a lane lives only in Reminders (sessions) — exactly
what `rbridge status` / `lint` already do from a one-shot process. Never writes:
actions stay in rbridge / the daemon, so this is safe in the `serve` child
without racing the poll loop's writes.

One function per view; each returns a plain dict (rendered to markdown or served
as JSON by `dashpages` / `server`).
"""

import datetime as _dt
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import activity as activity_module
from . import beads as beads_module
from . import config as config_module
from . import ghostty as ghostty_module
from . import mailbox as mailbox_module
from . import projects as projects_module
from . import reminders as reminders_module
from . import state as state_module
from . import transcript as transcript_module

_SESSION_LISTS = (
    ("claude", "RBRIDGE_CLAUDE_LIST", "_rb_claude_sessions"),
    ("codex", "RBRIDGE_CODEX_LIST", "_rb_codex_sessions"),
)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _projects(cfg: config_module.Config) -> list[projects_module.Project]:
    return projects_module.filter_existing(
        projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
    )


def _counts(issues: list[beads_module.Issue]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.status] = counts.get(issue.status, 0) + 1
    return counts


def _beads(project: projects_module.Project) -> tuple[list[beads_module.Issue], str | None]:
    try:
        return beads_module.list_issues(project.path), None
    except RuntimeError as e:
        return [], str(e)


def _flag(body: str, key: str) -> bool:
    m = re.search(rf"\b{key}\s*:\s*(\w+)", body, re.IGNORECASE)
    return bool(m and m.group(1).lower() in ("true", "yes", "1"))


def _session_mode(body: str) -> str:
    if _flag(body, "fixer"):
        return "fixer"
    if _flag(body, "capture"):
        return "capture"
    if _flag(body, "chat"):
        return "chat"
    return "interactive"


def _config(cfg: config_module.Config) -> dict[str, Any]:
    return {
        "registry_path": str(cfg.registry_path),
        "poll_interval_s": cfg.poll_interval_s,
        "list_prefix": cfg.list_prefix,
        "statuses": list(cfg.statuses),
    }


def sessions(cfg: config_module.Config) -> dict[str, Any]:
    out = []
    for engine, env, default in _SESSION_LISTS:
        try:
            rems = reminders_module.list_reminders(os.getenv(env, default))
        except RuntimeError:
            rems = []
        for r in rems:
            out.append({
                "engine": engine,
                "title": r.name,
                "completed": r.completed,
                "mode": _session_mode(r.body),
                "body": r.body[:600],
            })
    return {"generated_at": _now(), "sessions": out}


def tabs(cfg: config_module.Config) -> dict[str, Any]:
    out = []
    for t in ghostty_module.discover():
        s = transcript_module.resolve(t.pid, t.cwd)
        out.append({
            "pid": t.pid,
            "tty": t.tty,
            "mode": t.mode,
            "cwd": t.cwd,
            "session": s.session_id[:8] if s else "",
            "title": s.title if s else "",
        })
    return {"generated_at": _now(), "tabs": out}


def voice(cfg: config_module.Config) -> dict[str, Any]:
    out = [
        {
            "slug": mb.slug,
            "kind": mb.kind,
            "created_at": mb.created_at,
            "list_name": mb.list_name,
            "root": mb.source_cwd,
        }
        for mb in mailbox_module.list_active()
    ]
    return {"generated_at": _now(), "mailboxes": out}


def activity_view(cfg: config_module.Config, limit: int = 200) -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "activity": list(reversed(activity_module.entries()))[:limit],
    }


def project_view(cfg: config_module.Config, name: str) -> dict[str, Any] | None:
    proj = next((p for p in _projects(cfg) if p.name == name), None)
    if proj is None:
        return None
    issues, err = _beads(proj)
    ps = state_module.load(cfg.state_path).projects.get(str(proj.path))
    linked = set(ps.links) if ps else set()
    return {
        "generated_at": _now(),
        "name": proj.name,
        "path": str(proj.path),
        "list_name": proj.list_name,
        "error": err,
        "counts": _counts(issues),
        "beads": [
            {
                "id": i.id,
                "title": i.title,
                "status": i.status,
                "priority": i.priority,
                "type": i.issue_type,
                "linked": i.id in linked,
                "description": i.description[:300],
            }
            for i in issues
        ],
    }


def overview(cfg: config_module.Config) -> dict[str, Any]:
    state = state_module.load(cfg.state_path)
    projs = _projects(cfg)
    # `bd list` per project is the dominant cost; fan it out (subprocess → no GIL
    # contention) so the overview is ~one bd call, not the sum of all. Tab/voice
    # counts (also subprocess/file work) run concurrently in the same pool.
    with ThreadPoolExecutor(max_workers=12) as ex:
        f_tabs = ex.submit(ghostty_module.count)
        f_voice = ex.submit(lambda: len(mailbox_module.list_active()))
        beaded = list(ex.map(lambda p: (p, *_beads(p)), projs))
        tabs_count = f_tabs.result()
        voice_count = f_voice.result()
    rows = []
    agg: dict[str, int] = {}
    for p, issues, err in beaded:
        counts = _counts(issues)
        for k, v in counts.items():
            agg[k] = agg.get(k, 0) + v
        ps = state.projects.get(str(p.path))
        rows.append({
            "name": p.name,
            "total": len(issues),
            "counts": counts,
            "linked": len(ps.links) if ps else 0,
            "error": err,
        })
    sess = sessions(cfg)["sessions"]  # EventKit read — keep on the handler thread
    return {
        "generated_at": _now(),
        "config": _config(cfg),
        "totals": {
            "projects": len(rows),
            "beads": agg,
            "sessions_pending": sum(1 for s in sess if not s["completed"]),
            "tabs": tabs_count,  # count only — no per-tab transcript resolve
            "voice": voice_count,
        },
        "projects": rows,
        "activity": list(reversed(activity_module.entries()))[:20],
    }
