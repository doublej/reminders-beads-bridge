"""Persistent map of bead_id ↔ reminder_id per project."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import atomicio as atomicio_module


@dataclass
class Link:
    reminder_id: str
    bead_status: str
    reminder_completed: bool


@dataclass
class ProjectState:
    list_name: str
    links: dict[str, Link] = field(default_factory=dict)


@dataclass
class State:
    projects: dict[str, ProjectState] = field(default_factory=dict)


def load(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return State()
    projects: dict[str, ProjectState] = {}
    for project_path, p in data.get("projects", {}).items():
        links = {
            bead_id: Link(
                reminder_id=link["reminder_id"],
                bead_status=link.get("bead_status", ""),
                reminder_completed=link.get("reminder_completed", False),
            )
            for bead_id, link in p.get("links", {}).items()
        }
        projects[project_path] = ProjectState(
            list_name=p.get("list_name", ""),
            links=links,
        )
    return State(projects=projects)


def save(path: Path, state: State) -> None:
    data: dict[str, Any] = {
        "projects": {
            project_path: {
                "list_name": p.list_name,
                "links": {
                    bead_id: {
                        "reminder_id": link.reminder_id,
                        "bead_status": link.bead_status,
                        "reminder_completed": link.reminder_completed,
                    }
                    for bead_id, link in p.links.items()
                },
            }
            for project_path, p in state.projects.items()
        }
    }
    atomicio_module.atomic_write_text(path, json.dumps(data, indent=2))
