"""Projects list: one reminder per registered project. Completed = hide from sync."""

import logging
from pathlib import Path

from . import activity as activity_module
from . import projects as projects_module
from . import reminders as reminders_module
from . import state as state_module

log = logging.getLogger(__name__)

_LIST_SUFFIX = "Projects"


def list_name(prefix: str) -> str:
    return f"{prefix}{_LIST_SUFFIX}"


def _body(project: projects_module.Project) -> str:
    return (
        f"{project.path}\n\n"
        "Check to hide this project from sync. Uncheck to resume."
    )


def sync(prefix: str, active: list[projects_module.Project]) -> set[str]:
    """Reconcile master list. Return set of project names that are hidden."""
    ln = list_name(prefix)
    reminders_module.create_list(ln)
    remote = reminders_module.list_reminders(ln)
    by_name: dict[str, list[reminders_module.Reminder]] = {}
    for r in remote:
        by_name.setdefault(r.name, []).append(r)

    expected = {p.name for p in active}
    batch = reminders_module.Batch()
    hidden: set[str] = set()

    for project in active:
        body = _body(project)
        matches = by_name.get(project.name, [])
        if not matches:
            batch.creates.append({"name": project.name, "body": body, "priority": 0})
            continue
        keep, extras = matches[0], matches[1:]
        for extra in extras:
            batch.deletes.append(extra.id)
        if keep.completed:
            hidden.add(project.name)
        if keep.body != body:
            batch.updates.append({"id": keep.id, "body": body})

    for name, matches in by_name.items():
        if name in expected:
            continue
        for r in matches:
            batch.deletes.append(r.id)

    if not batch.empty():
        reminders_module.apply_batch(ln, batch)
    return hidden


def apply_hides(
    active: list[projects_module.Project],
    hidden: set[str],
    state: state_module.State,
    state_path: Path,
) -> None:
    """Delete reminders lists for hidden projects; drop their links from state."""
    dirty = False
    for project in active:
        if project.name not in hidden:
            continue
        try:
            if reminders_module.delete_list(project.list_name):
                log.info(
                    "%s hidden — deleted list %r",
                    project.name,
                    project.list_name,
                )
                activity_module.record(
                    project.name, "hidden", "", f"deleted list {project.list_name}"
                )
        except RuntimeError as e:
            log.warning("Delete list failed for %s: %s", project.name, e)
        if state.projects.pop(str(project.path), None) is not None:
            dirty = True
    if dirty:
        state_module.save(state_path, state)
