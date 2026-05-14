"""Spawn a Claude Code or Codex session in a new Ghostty window with a prefilled prompt."""

import os
import shutil
import subprocess
from pathlib import Path

_GHOSTTY_APP_BUNDLE = "/Applications/Ghostty.app"

_USER_BIN_DIRS = (
    "~/.local/bin",
    "~/.bun/bin",
    "~/.cargo/bin",
    "~/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


def ghostty_bundle() -> str:
    override = os.getenv("RBRIDGE_GHOSTTY_APP")
    if override and Path(override).exists():
        return override
    if Path(_GHOSTTY_APP_BUNDLE).exists():
        return _GHOSTTY_APP_BUNDLE
    raise RuntimeError(
        "Ghostty.app not found at /Applications/Ghostty.app. "
        "Install it or set RBRIDGE_GHOSTTY_APP to its .app path."
    )


def session_bin(cmd: str) -> str:
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


def launch(cwd: Path, prompt: str, *, cmd: str = "claude") -> None:
    bundle = ghostty_bundle()
    inner = [session_bin(cmd)]
    if prompt:
        inner.append(prompt)
    args = [
        "/usr/bin/open",
        "-na",
        bundle,
        "--args",
        f"--working-directory={cwd}",
        "-e",
        *inner,
    ]
    subprocess.Popen(args, start_new_session=True)
