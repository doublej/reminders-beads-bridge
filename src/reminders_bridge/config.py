"""Configuration for reminders-bridge."""

from dataclasses import dataclass
import os
from pathlib import Path

from . import body as body_module


@dataclass
class Config:
    registry_path: Path
    state_path: Path
    poll_interval_s: float
    list_prefix: str
    statuses: tuple[str, ...]
    api_url: str
    api_timeout_s: float


def load() -> Config:
    statuses_env = os.getenv("RBRIDGE_STATUSES", "open,in_progress")
    statuses = tuple(s.strip() for s in statuses_env.split(",") if s.strip())
    unknown = [s for s in statuses if s not in body_module.VALID_STATUSES]
    if unknown:
        raise RuntimeError(
            f"RBRIDGE_STATUSES contains unknown status(es): {unknown}. "
            f"Valid: {sorted(body_module.VALID_STATUSES)}"
        )
    return Config(
        registry_path=Path(
            os.getenv("RBRIDGE_REGISTRY", "~/.beads-kanban-projects.json")
        ).expanduser(),
        state_path=Path(
            os.getenv("RBRIDGE_STATE", "~/.claude/reminders-bridge-state.json")
        ).expanduser(),
        poll_interval_s=float(os.getenv("RBRIDGE_POLL_S", "30")),
        list_prefix=os.getenv("RBRIDGE_LIST_PREFIX", "Beads: "),
        statuses=statuses,
        api_url=os.getenv("RBRIDGE_API_URL", "http://localhost:5173"),
        api_timeout_s=float(os.getenv("RBRIDGE_API_TIMEOUT_S", "10")),
    )
