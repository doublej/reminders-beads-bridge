"""Classify a child pid's liveness, distinguishing our children from foreign pids.

After a daemon restart, detached children (`start_new_session=True`) are
reparented to init, so `waitpid` raises `ChildProcessError`. We must not fall
back to `os.kill(pid, 0)` — a reused pid would read as alive and eventually get
`killpg`'d, signalling an unrelated process group.
"""

import os


def child_state(pid: int) -> str:
    """Return ``running`` (our child, not yet reaped), ``dead`` (reaped/gone),
    or ``foreign`` (not our child — reparented after a restart)."""
    try:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return "foreign"
    except OSError:
        return "dead"
    return "dead" if reaped == pid else "running"
