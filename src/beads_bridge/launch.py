"""Spawn a Claude Code or Codex session in a new Ghostty window with a prefilled prompt."""

import os
import subprocess
from pathlib import Path

_GHOSTTY_APP_BUNDLE = "/Applications/Ghostty.app"


def ghostty_bundle() -> str:
    override = os.getenv("BBRIDGE_GHOSTTY_APP")
    if override and Path(override).exists():
        return override
    if Path(_GHOSTTY_APP_BUNDLE).exists():
        return _GHOSTTY_APP_BUNDLE
    raise RuntimeError(
        "Ghostty.app not found at /Applications/Ghostty.app. "
        "Install it or set BBRIDGE_GHOSTTY_APP to its .app path."
    )


def session_bin(cmd: str) -> str:
    env_var = {"claude": "BBRIDGE_CLAUDE_BIN", "codex": "BBRIDGE_CODEX_BIN"}.get(cmd)
    if env_var:
        override = os.getenv(env_var)
        if override:
            return override
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
