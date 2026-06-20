"""Daemon-managed lifecycle for the `rbridge serve` subprocess.

The `Dashboard server` setting toggles it: the daemon calls `ensure(enabled)`
each cycle. When on, it spawns `serve` as a child (and respawns if it died);
when off, it reaps the child. The server is the daemon's child, so it shares the
daemon's lifecycle — `_restart` reaps it before re-exec so the new daemon can
re-bind the port cleanly.

Robustness: if the port is already being served (e.g. an orphan from a crashed
daemon), `ensure` adopts it instead of spawning a second one that would fail to
bind and crash-loop.
"""

import logging
import subprocess
import sys

from . import dashboard as dashboard_module

log = logging.getLogger(__name__)

_proc: subprocess.Popen | None = None


def is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def ensure(enabled: bool) -> None:
    global _proc
    if enabled:
        if is_running():
            return
        _proc = None
        if dashboard_module.alive():  # already served (orphan / external) — adopt it
            return
        _proc = subprocess.Popen([sys.argv[0], "serve"])
        log.info("Dashboard server started (pid %d)", _proc.pid)
        return
    proc = _proc
    if proc is None or proc.poll() is not None:
        _proc = None
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.info("Dashboard server stopped")
    _proc = None
