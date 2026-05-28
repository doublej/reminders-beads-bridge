"""Path sandbox for voice-mailbox file navigation.

Confines every fetch/grep/tree request to the mailbox's repo root. The phone
can submit arbitrary path strings, so this is the security boundary: absolute
paths, `..`/symlink escapes, dotfiles, and secret-shaped files are rejected
before any read happens.
"""

import fnmatch
import os
from pathlib import Path

BINARY_SUFFIXES = {
    ".so", ".dylib", ".o", ".a", ".bin", ".exe", ".dll", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar", ".whl",
    ".pyc", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mov", ".wav", ".mp3",
}
# Dot-prefixed dirs/files are blocked by the blanket rule below; only non-dot
# directories need to be named explicitly.
_DENIED_DIRS = {"node_modules", "__pycache__"}
_DENIED_GLOBS = (
    "*.pem", "*.key", "*.p12", "*.pfx", "*.crt", "id_rsa*", "id_ed25519*",
    "id_ecdsa*", "*.sqlite", "*.sqlite3", "*.db", "credentials*",
)


class NavError(Exception):
    """A navigation request was refused (bad path, blocked file, too big)."""


def nav_enabled() -> bool:
    return os.getenv("RBRIDGE_VOICE_NAV", "true").lower() not in {"false", "0", "no"}


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def denied_component(name: str) -> bool:
    """True if a single path component must never be exposed."""
    if name.startswith("."):
        return True
    low = name.lower()
    return low in _DENIED_DIRS or any(fnmatch.fnmatch(low, g) for g in _DENIED_GLOBS)


def safe_resolve(root: Path, relpath: str) -> Path:
    """Resolve `relpath` under `root` or raise NavError. The only entry point."""
    rp = relpath.strip()
    if not rp:
        raise NavError("empty path")
    if rp.startswith("~") or Path(rp).is_absolute():
        raise NavError("absolute paths are not allowed")
    root_resolved = root.resolve()
    resolved = (root_resolved / rp).resolve()  # collapses `..` and follows symlinks
    try:
        parts = resolved.relative_to(root_resolved).parts
    except ValueError:
        raise NavError("path escapes the repo root") from None
    for part in parts:
        if denied_component(part):
            raise NavError(f"blocked component: {part}")
    return resolved


def walk_files(root: Path):
    """Yield text-ish files under root, pruning denied dirs/files in place."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not denied_component(d)]
        for fn in filenames:
            if denied_component(fn):
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() not in BINARY_SUFFIXES:
                yield p
