"""One-time, lossless list renames into the ``_rb_`` naming convention.

Every bridge-managed list now lives under a single ``_rb_`` namespace so it
sorts together and reads as system-owned in the Reminders sidebar. Only
genuinely beads-scoped lists keep a ``beads`` segment (``_rb_beads_*``).

Migration is **rename, not delete+recreate**: renaming an EventKit calendar
preserves every reminder it holds and the user state encoded in them —
``<bb:notes>`` on project tasks, completion = hidden on the projects index,
completion/value bodies on settings. ``reminders.rename_list`` is a no-op once
the old list is gone, so running this every cycle is cheap and idempotent.

Voice lists are deliberately excluded: their list name is stored per-exchange
in state, so existing exchanges keep working under their old name and only new
exchanges adopt ``_rb_voice_`` (see ``mailbox.voice_list_prefix``).
"""

from . import projects as projects_module
from . import reminders as reminders_module

# (old name) -> (new name) for the fixed, singleton lists.
_STATIC: tuple[tuple[str, str], ...] = (
    ("rbridge: Settings", "_rb_settings"),
    ("Beads: Settings", "_rb_settings"),
    ("! Beads: Readme", "!_rb_readme"),
    ("Beads: Activity", "_rb_activity"),
    ("Beads: Projects", "_rb_beads_projects"),
    ("Claude: Sessions", "_rb_claude_sessions"),
    ("Codex: Sessions", "_rb_codex_sessions"),
    ("Claude: Tabs", "_rb_claude_tabs"),
)
_OLD_PROJECT_PREFIX = "Beads: "


def _rename(old: str, new: str) -> None:
    try:
        reminders_module.rename_list(old, new)
    except RuntimeError:
        pass


def run(prefix: str, projects: list[projects_module.Project]) -> None:
    """Rename any surviving pre-``_rb_`` lists to the new convention."""
    for old, new in _STATIC:
        _rename(old, new)
    for p in projects:
        _rename(f"{_OLD_PROJECT_PREFIX}{p.name}", f"{prefix}{p.name}")
