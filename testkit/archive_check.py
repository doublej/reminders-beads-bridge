"""Assert closing a voice exchange never destroys undrained responses.

`close()` deletes the Reminders list, the mirror and the state file. Before
this check existed, a `done` reminder could wipe a 25-minute interview in the
one-minute window before the project agent ran `rbridge mailbox read`. The
archive is what makes that survivable, so:

  1. close writes `<slug>.responses.json` with every response,
  2. `read()` still serves them once the mailbox is gone,
  3. a failed drain (Reminders unavailable) still closes, and says so.

Run: uv run python testkit/archive_check.py
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="rbridge-archive-check-")
os.environ["RBRIDGE_MAILBOX_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reminders_bridge import mailbox  # noqa: E402


@dataclass
class FakeReminder:
    id: str
    name: str
    body: str = ""
    completed: bool = False


class FakeReminders:
    def __init__(self, rems, fail=False):
        self.rems, self.fail, self.deleted = rems, fail, []

    def list_reminders(self, name):
        if self.fail:
            raise RuntimeError("Reminders unavailable")
        return self.rems

    def delete_list(self, name):
        self.deleted.append(name)
        return True


class FakeMirror:
    def delete(self, slug):
        pass


class FakeActivity:
    def __init__(self):
        self.lines = []

    def record(self, list_name, kind, _, detail):
        self.lines.append(f"{kind} {detail}")


def seed(slug, rems, fail=False):
    mailbox._STATE_DIR.mkdir(parents=True, exist_ok=True)
    mailbox._save(
        mailbox.Mailbox(
            slug=slug,
            list_name=mailbox.list_name_for(slug),
            brief_path=str(mailbox._brief_path(slug)),
            created_at="2026-09-08T13:17:20+00:00",
            kind="REMINDERS",
        )
    )
    mailbox._brief_path(slug).write_text("brief")
    mailbox.reminders_module = FakeReminders(rems, fail=fail)
    mailbox.mirror_module = FakeMirror()
    act = FakeActivity()
    mailbox.activity_module = act
    return act


def check_drain_before_delete():
    slug = "interview"
    act = seed(
        slug,
        [
            FakeReminder("h", mailbox.HEADER_TITLE, "header"),
            FakeReminder("b", f"Brief for {slug}", "brief"),
            FakeReminder("n", "fetch: src/foo.py"),
            FakeReminder("1", "Decision: Q2 delete", "yes, delete it"),
            FakeReminder("2", "Question: Q7 colima", "what is in the VM image?"),
            FakeReminder("d", "Done"),
        ],
    )
    res = mailbox.close(slug, reason="done-reminder")
    assert res.found and res.list_deleted and res.state_deleted, res
    assert res.archived == 2, res.archived  # the `done` marker is not a response

    arch = json.loads(mailbox._archive_path(slug).read_text())
    assert arch["close_reason"] == "done-reminder" and arch["closed_at"], arch
    assert [r["kind"] for r in arch["responses"]] == [
        "decision", "question", "done",
    ], arch["responses"]
    assert arch["responses"][0]["body"] == "yes, delete it", arch

    # the list, mirror and state are gone — read must still serve the answers
    assert mailbox._load(slug) is None
    out = mailbox.read(slug)
    assert out["has_done"] is True and len(out["responses"]) == 3, out
    assert out["closed_at"] == arch["closed_at"], out
    assert [d["slug"] for d in mailbox.list_closed()] == [slug]
    assert mailbox.list_active() == []
    assert any("2 responses archived" in ln for ln in act.lines), act.lines
    print(f"ok  drain-before-delete: {res.archived} archived, read() still serves")


def check_drain_failure_still_closes():
    slug = "unreadable"
    act = seed(slug, [], fail=True)
    res = mailbox.close(slug, reason="cli")
    assert res.found and res.archived is None and res.state_deleted, res
    assert not mailbox._archive_path(slug).exists()
    assert any("archive FAILED" in ln for ln in act.lines), act.lines
    print("ok  drain failure closes anyway and is recorded")


if __name__ == "__main__":
    check_drain_before_delete()
    check_drain_failure_still_closes()
    print(f"all checks passed ({_TMP})")
