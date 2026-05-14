"""HTTP client for the beads-kanban API.

Wraps the endpoints defined in `_management/beads-kanban/docs/API.md`.
Envelope is unwrapped: on `ok:false`, raises APIError(code, message).
Callers own retry / backoff; this module is pure request/response.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class APIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.api_message = message


def _q(project: Path | None, **extra: str) -> str:
    params: dict[str, str] = {}
    if project is not None:
        params["project"] = str(project)
    params.update({k: v for k, v in extra.items() if v is not None})
    return "?" + urllib.parse.urlencode(params) if params else ""


@dataclass
class Client:
    base_url: str
    timeout_s: float = 10.0

    def _req(self, method: str, path: str, body: dict | None = None) -> Any:
        url = self.base_url.rstrip("/") + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                payload = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read() or b"{}")
            except (json.JSONDecodeError, ValueError):
                raise APIError("HTTP", f"{e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise APIError("NETWORK", str(e.reason)) from e
        except TimeoutError as e:
            raise APIError("TIMEOUT", str(e)) from e
        if not payload.get("ok"):
            err = payload.get("error") or {}
            raise APIError(err.get("code", "UNKNOWN"), err.get("message", "unknown error"))
        return payload.get("data", {})

    # issues
    def list_issues(self, project: Path) -> list[dict]:
        return self._req("GET", f"/api/issues{_q(project)}")["issues"]

    def create_issue(self, project: Path, fields: dict) -> dict:
        return self._req("POST", f"/api/issues{_q(project)}", fields)

    def patch_issue(self, project: Path, issue_id: str, fields: dict) -> dict:
        return self._req("PATCH", f"/api/issues/{issue_id}{_q(project)}", fields)

    def close_issue(self, project: Path, issue_id: str, reason: str = "Completed") -> dict:
        return self._req("POST", f"/api/issues/{issue_id}/close{_q(project)}", {"reason": reason})

    def delete_issue(self, project: Path, issue_id: str) -> dict:
        return self._req("DELETE", f"/api/issues/{issue_id}{_q(project)}")

    # comments / deps / per-issue agent sessions
    def list_comments(self, project: Path, issue_id: str) -> list[dict]:
        return self._req("GET", f"/api/issues/{issue_id}/comments{_q(project)}")["comments"]

    def add_comment(self, project: Path, issue_id: str, text: str) -> dict:
        return self._req("POST", f"/api/issues/{issue_id}/comments{_q(project)}", {"text": text})

    def add_dep(self, project: Path, issue_id: str, depends_on: str, dep_type: str = "blocks") -> dict:
        body = {"depends_on": depends_on, "dep_type": dep_type}
        return self._req("POST", f"/api/issues/{issue_id}/deps{_q(project)}", body)

    def remove_dep(self, project: Path, issue_id: str, depends_on: str) -> dict:
        return self._req("DELETE", f"/api/issues/{issue_id}/deps{_q(project)}", {"depends_on": depends_on})

    def issue_agent_sessions(self, project: Path, issue_id: str) -> list[dict]:
        return self._req("GET", f"/api/issues/{issue_id}/agent-sessions{_q(project)}")["sessions"]

    # agents (worker-level)
    def agents_snapshot(self, project: Path) -> dict:
        return self._req("GET", f"/api/agents{_q(project)}")

    def agents_start(self, project: Path, ticket_id: str, **opts: Any) -> dict:
        return self._req("POST", f"/api/agents{_q(project)}", {"ticketId": ticket_id, **opts})

    def agent_get(self, session_id: str) -> dict:
        return self._req("GET", f"/api/agents/{session_id}")

    def agent_interrupt(self, session_id: str) -> dict:
        return self._req("DELETE", f"/api/agents/{session_id}")

    def agent_message(self, session_id: str, text: str) -> dict:
        return self._req("POST", f"/api/agents/{session_id}/message", {"text": text})

    def agent_session_history(
        self, session_id: str, project: Path, since: int | None = None
    ) -> list[dict]:
        extra = {"since": str(since)} if since is not None else {}
        path = f"/api/agent-sessions/{session_id}/history{_q(project, **extra)}"
        return self._req("GET", path)["messages"]

    # worker process
    def agent_worker(self, action: str) -> dict:
        if action not in ("start", "stop", "restart"):
            raise ValueError(f"agent_worker action must be start|stop|restart, got {action!r}")
        return self._req("POST", "/api/agent", {"action": action})

    # misc
    def agent_health(self) -> bool:
        return bool(self._req("GET", "/api/agent/health").get("healthy"))

    def cwd_get(self) -> dict:
        return self._req("GET", "/api/cwd")

    def cwd_set(self, path: Path) -> dict:
        return self._req("POST", "/api/cwd", {"path": str(path)})

    def projects_list(self) -> list[dict]:
        return self._req("GET", "/api/projects")["projects"]

    def worktrees(self, project: Path) -> list[dict]:
        return self._req("GET", f"/api/worktrees{_q(project)}")["worktrees"]

    def events_since(self, project: Path, since_ms: int, limit: int = 100) -> list[dict]:
        return self._req("GET", f"/api/events{_q(project, since=str(since_ms), limit=str(limit))}")["events"]
