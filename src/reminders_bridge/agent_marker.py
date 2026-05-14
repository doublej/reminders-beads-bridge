"""Dispatch !agent markers found in reminder bodies to the beads-kanban API."""

import datetime as _dt
import logging

from . import activity as activity_module
from . import api as api_module
from . import beads as beads_module
from . import projects as projects_module

log = logging.getLogger(__name__)


def dispatch(
    client: api_module.Client,
    project: projects_module.Project,
    issue: beads_module.Issue,
    args: dict[str, str],
) -> str:
    opts: dict = {}
    if "model" in args:
        opts["model"] = args["model"]
    if args.get("useWorktree", "").lower() in ("1", "true", "yes"):
        opts["useWorktree"] = True
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    try:
        try:
            client.agent_worker("start")
        except api_module.APIError:
            pass
        client.agents_start(project.path, issue.id, **opts)
    except api_module.APIError as e:
        log.warning("Agent launch failed for %s: %s", issue.id, e)
        activity_module.record(project.name, "agent-error", issue.id, e.code)
        return f'<bb:agent error="{e.code}" at="{ts}"/>'
    log.info("Agent queued for %s", issue.id)
    activity_module.record(project.name, "agent-queued", issue.id, "via !agent marker")
    return f'<bb:agent queued="{issue.id}" at="{ts}"/>'
