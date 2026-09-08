"""Assert the reconcile gate's change signal still holds.

The gate in `daemon._beads_quiet` skips `bd list` — and therefore reaps the
`dolt sql-server` — whenever `beads.journal_size` is unchanged. Two properties
carry the whole design, and both are `bd`/Dolt implementation details that a
`bd` upgrade could break silently:

  1. write-sensitive  — every mutation moves the journal, or the bridge goes
     blind to bead changes.
  2. lifecycle-blind  — server start/stop does NOT move it, or the reaper
     restarts what it just stopped, every cycle.

Run against a real server-mode beads repo (creates + deletes one probe bead):

    uv run python testkit/gate_check.py [repo-path]
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reminders_bridge import beads  # noqa: E402


def bd(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(["bd", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"bd {' '.join(args)} failed: {r.stderr.strip()}"
    return r


def main(cwd: Path) -> None:
    size = beads.journal_size(cwd)
    assert size is not None, f"no Dolt journal under {cwd}/.beads — cannot gate"

    def settled() -> int:
        time.sleep(1.0)
        s = beads.journal_size(cwd)
        assert s is not None
        return s

    # lifecycle-blind: stop and cold-start must leave the signal alone.
    bd(cwd, "dolt", "stop")
    assert settled() == size, "journal moved on `bd dolt stop` — reaper would loop"
    bd(cwd, "list", "--json", "--all")
    assert settled() == size, "journal moved on server start — reaper would loop"
    assert beads.server_pid(cwd), "server did not come back after `bd dolt stop`"

    # write-sensitive: every mutation the bridge can cause must move it.
    import json

    r = bd(cwd, "create", "gate-check-probe", "-p", "3", "--json")
    raw = json.loads(r.stdout)
    issue_id = raw.get("issue", raw)["id"]
    try:
        for op in (
            ["close", issue_id, "-m", "probe"],
            ["reopen", issue_id, "-r", "probe"],
            ["note", issue_id, "probe"],
        ):
            before = settled()
            bd(cwd, *op)
            assert settled() != before, f"journal did not move on `bd {op[0]}`"
    finally:
        bd(cwd, "delete", issue_id, "--force")
    assert settled() != size, "journal did not move on `bd create`"

    print(f"gate_check OK ({cwd})")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
