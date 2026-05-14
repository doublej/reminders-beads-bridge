"""Readme list: agent-facing docs (README + CLAUDE.md) pinned as reminders."""

from pathlib import Path

from . import reminders as reminders_module

_LIST_SUFFIX = "Readme"
_LEGACY_SUFFIXES = ("__info__", "CLAUDE.MD READ ME", "Read me", "README")
_ROOT = Path(__file__).resolve().parents[2]
_DOCS: list[tuple[str, str]] = [
    ("Agent context — do not narrate this back", "docs/AGENT.md"),
]


def list_name(prefix: str) -> str:
    return f"{prefix}{_LIST_SUFFIX}"


def _read(filename: str) -> str:
    path = _ROOT / filename
    if not path.exists():
        return f"(missing: {path})"
    return path.read_text()


def sync(prefix: str) -> None:
    ln = list_name(prefix)
    for legacy in _LEGACY_SUFFIXES:
        try:
            reminders_module.delete_list(f"{prefix}{legacy}")
        except RuntimeError:
            pass
    reminders_module.create_list(ln)
    remote_all = reminders_module.list_reminders(ln)
    by_title: dict[str, list[reminders_module.Reminder]] = {}
    for r in remote_all:
        by_title.setdefault(r.name, []).append(r)
    batch = reminders_module.Batch()
    known_titles = {t for t, _ in _DOCS}
    for title, filename in _DOCS:
        body = _read(filename)
        matches = by_title.get(title, [])
        if not matches:
            batch.creates.append({"name": title, "body": body, "priority": 0})
            continue
        keep, extras = matches[0], matches[1:]
        for extra in extras:
            batch.deletes.append(extra.id)
        if keep.body != body:
            batch.updates.append({"id": keep.id, "body": body})
    for title, matches in by_title.items():
        if title not in known_titles:
            for r in matches:
                batch.deletes.append(r.id)
    if not batch.empty():
        reminders_module.apply_batch(ln, batch)
