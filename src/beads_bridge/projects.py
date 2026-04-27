"""Read the beads-kanban project registry."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Project:
    path: Path
    name: str
    list_name: str


_SAFE_NAME = re.compile(r"[\x00-\x1f\"]")


def _sanitize(name: str) -> str:
    return _SAFE_NAME.sub("", name).strip()


def load_projects(registry_path: Path, list_prefix: str) -> list[Project]:
    if not registry_path.exists():
        return []
    try:
        raw = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    projects: list[Project] = []
    for entry in raw:
        path = Path(entry["path"]).expanduser()
        name = _sanitize(entry.get("name") or path.name)
        if not name:
            continue
        projects.append(
            Project(path=path, name=name, list_name=f"{list_prefix}{name}")
        )
    return projects


def filter_existing(projects: list[Project]) -> list[Project]:
    return [p for p in projects if (p.path / ".beads").is_dir()]
