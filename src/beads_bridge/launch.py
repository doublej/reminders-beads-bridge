"""Spawn a Claude Code or Codex session in a new Ghostty window with a prefilled prompt."""

import os
import shutil
import subprocess
from pathlib import Path

_GHOSTTY_APP = "/Applications/Ghostty.app/Contents/MacOS/ghostty"


def ghostty_bin() -> str:
    override = os.getenv("BBRIDGE_GHOSTTY_BIN")
    if override and Path(override).exists():
        return override
    if Path(_GHOSTTY_APP).exists():
        return _GHOSTTY_APP
    found = shutil.which("ghostty")
    if found:
        return found
    raise RuntimeError(
        "Ghostty not found. Install Ghostty.app, set BBRIDGE_GHOSTTY_BIN, "
        "or put `ghostty` on $PATH."
    )


def session_bin(cmd: str) -> str:
    env_var = {"claude": "BBRIDGE_CLAUDE_BIN", "codex": "BBRIDGE_CODEX_BIN"}.get(cmd)
    if env_var:
        override = os.getenv(env_var)
        if override:
            return override
    return cmd


def launch(cwd: Path, prompt: str, *, cmd: str = "claude") -> None:
    args = [ghostty_bin(), f"--working-directory={cwd}", "-e", session_bin(cmd)]
    if prompt:
        args.append(prompt)
    subprocess.Popen(args, start_new_session=True)
