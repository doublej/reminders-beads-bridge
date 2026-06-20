"""`rbridge serve`: read-only HTTP at-a-glance view of the bridge.

Token-gated (see `dashboard.py`). Compact markdown by default (the primary
reader is an agent fetching the URL); `?format=json` for structured reads. Paths
are the drill-down: `/`, `/project/<name>`, `/sessions`, `/tabs`, `/voice`,
`/activity`. No writes — actions go through rbridge. Binds whatever
`RBRIDGE_DASHBOARD_HOST` says (loopback by default; `0.0.0.0` behind a reverse
proxy).
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import config as config_module
from . import dashboard as dashboard_module
from . import dashhtml as dashhtml_module
from . import dashpages as dashpages_module
from . import reminders as reminders_module
from . import snapshot as snapshot_module


def _route(path: str, cfg: config_module.Config) -> tuple[dict[str, Any] | None, str]:
    """Map a path to (view-dict, view-key). dict None ⇒ 404."""
    if path in ("/", ""):
        return snapshot_module.overview(cfg), "overview"
    if path == "/sessions":
        return snapshot_module.sessions(cfg), "sessions"
    if path == "/tabs":
        return snapshot_module.tabs(cfg), "tabs"
    if path == "/voice":
        return snapshot_module.voice(cfg), "voice"
    if path == "/activity":
        return snapshot_module.activity_view(cfg), "activity"
    if path.startswith("/project/"):
        name = unquote(path[len("/project/"):]).strip("/")
        return snapshot_module.project_view(cfg, name), "project"
    return None, "overview"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # silence default stderr logging
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        token = (query.get("t") or [""])[0]
        if not dashboard_module.valid(token):
            self._send(403, "text/plain", b"forbidden: missing or expired token")
            return
        cfg = config_module.load()
        with reminders_module.autorelease_pool():
            data, view = _route(parsed.path, cfg)
            reminders_module.reset_store()
        if data is None:
            self._send(404, "text/plain", b"not found")
            return
        fmt = (query.get("format") or [""])[0]
        if fmt == "json":
            self._send(200, "application/json", json.dumps(data, indent=2).encode())
        elif fmt == "html" or "html" in query:
            html = dashhtml_module.RENDER[view](data, token)
            self._send(200, "text/html; charset=utf-8", html.encode())
        else:
            md = dashpages_module.RENDER[view](data, token)
            self._send(200, "text/markdown; charset=utf-8", md.encode())


def run(port: int | None = None, host: str | None = None) -> None:
    bind_host = host or dashboard_module.host()
    bind_port = port or dashboard_module.port()
    # Plain (serial) HTTPServer: requests are rare and each may touch the shared
    # EventKit store; serializing avoids cross-handler store races.
    server = HTTPServer((bind_host, bind_port), _Handler)
    print(f"rbridge serve → bind {bind_host}:{bind_port}  (token required)")
    print(f"live URL: {dashboard_module.url()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
