"""Child-process helpers: pid liveness, and resolving the agent binary to run.

Classify a child pid's liveness, distinguishing our children from foreign pids.

After a daemon restart, detached children (`start_new_session=True`) are
reparented to init, so `waitpid` raises `ChildProcessError`. We must not fall
back to `os.kill(pid, 0)` — a reused pid would read as alive and eventually get
`killpg`'d, signalling an unrelated process group.
"""

import os
import shutil
from pathlib import Path


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


# Under launchd PATH is minimal, so `which` alone misses user-installed binaries.
_USER_BIN_DIRS = (
    "~/.local/bin",
    "~/.bun/bin",
    "~/.cargo/bin",
    "~/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


def session_bin(cmd: str) -> str:
    """Absolute path to the `claude` / `codex` binary, or `cmd` if not found."""
    env_var = {"claude": "RBRIDGE_CLAUDE_BIN", "codex": "RBRIDGE_CODEX_BIN"}.get(cmd)
    if env_var:
        override = os.getenv(env_var)
        if override:
            return override
    found = shutil.which(cmd)
    if found:
        return found
    for d in _USER_BIN_DIRS:
        candidate = Path(d).expanduser() / cmd
        if candidate.exists():
            return str(candidate)
    return cmd
