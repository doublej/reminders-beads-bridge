"""Read-only facade: assemble bridge state from on-disk sources.

Pure reads — registry (`projects.py`), the link map (`state.json`), `bd list`,
and the activity log — with **no EventKit**, so `rbridge serve` can render this
from a separate process without racing the daemon's poll loop. Writes never go
through here; actions stay in rbridge / the daemon.
"""

import datetime as _dt
from typing import Any

from . import activity as activity_module
from . import beads as beads_module
from . import config as config_module
from . import projects as projects_module
from . import state as state_module


def _project_view(
    project: projects_module.Project, state: state_module.State
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    total = 0
    bd_error: str | None = None
    try:
        issues = beads_module.list_issues(project.path)
    except RuntimeError as e:
        issues = []
        bd_error = str(e)
    for issue in issues:
        counts[issue.status] = counts.get(issue.status, 0) + 1
        total += 1
    ps = state.projects.get(str(project.path))
    return {
        "name": project.name,
        "path": str(project.path),
        "list_name": project.list_name,
        "counts": counts,
        "total": total,
        "linked": len(ps.links) if ps else 0,
        "bd_error": bd_error,
    }


def build(cfg: config_module.Config) -> dict[str, Any]:
    state = state_module.load(cfg.state_path)
    projects = projects_module.filter_existing(
        projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
    )
    return {
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "registry_path": str(cfg.registry_path),
            "poll_interval_s": cfg.poll_interval_s,
            "list_prefix": cfg.list_prefix,
            "statuses": list(cfg.statuses),
        },
        "projects": [_project_view(p, state) for p in projects],
        "activity": list(reversed(activity_module.entries()))[:50],
    }
