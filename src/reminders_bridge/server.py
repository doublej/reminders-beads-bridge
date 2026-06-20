"""`rbridge serve`: read-only HTTP at-a-glance view of the bridge.

Binds 127.0.0.1 only. Validates the rotating token (see `dashboard.py`) before
serving, then renders the snapshot (`snapshot.py`) as minimal HTML, or JSON with
`?format=json`. No writes — actions go through rbridge.
"""

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import config as config_module
from . import dashboard as dashboard_module
from . import snapshot as snapshot_module


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _render_html(data: dict[str, Any]) -> str:
    rows = []
    for p in data["projects"]:
        if p["bd_error"]:
            counts = '<span class="err">bd error</span>'
        else:
            pairs = ", ".join(f"{k}:{v}" for k, v in sorted(p["counts"].items()))
            counts = _esc(pairs or "—")
        rows.append(
            f"<tr><td>{_esc(p['name'])}</td><td>{p['total']}</td>"
            f"<td>{counts}</td><td>{p['linked']}</td>"
            f"<td class=path>{_esc(p['path'])}</td></tr>"
        )
    activity = "\n".join(
        f"{_esc(e['ts'])}  {_esc(e['project']):<18.18} {_esc(e['kind']):<9.9} "
        f"{_esc(e.get('bead_id') or '-'):<9.9} {_esc(e['detail'])}"
        for e in data["activity"]
    )
    cfg = data["config"]
    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>reminders-bridge</title>
<style>
body{{font:13px/1.5 ui-monospace,Menlo,monospace;margin:1.5rem;max-width:64rem}}
h1{{font-size:1rem}} h2{{font-size:.95rem}}
table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:.2rem .6rem;border-bottom:1px solid #ddd}}
th{{border-bottom:2px solid #999}} .path{{color:#888;font-size:.85em}}
.err{{color:#b00}} pre{{background:#f6f6f6;padding:.8rem;overflow:auto}}
.meta{{color:#888}}
</style></head><body>
<h1>reminders-bridge — at a glance</h1>
<p class=meta>generated {_esc(data['generated_at'])} · poll {cfg['poll_interval_s']}s ·
statuses {_esc(', '.join(cfg['statuses']))} · prefix {_esc(cfg['list_prefix'])}</p>
<table><tr><th>project</th><th>beads</th><th>by status</th><th>linked</th><th>path</th></tr>
{''.join(rows) or '<tr><td colspan=5>(no projects)</td></tr>'}
</table>
<h2>recent activity</h2>
<pre>{activity or '(no activity yet)'}</pre>
</body></html>"""


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
        if parsed.path not in ("/", ""):
            self._send(404, "text/plain", b"not found")
            return
        query = parse_qs(parsed.query)
        token = (query.get("t") or [""])[0]
        if not dashboard_module.valid(token):
            self._send(403, "text/plain", b"forbidden: missing or expired token")
            return
        data = snapshot_module.build(config_module.load())
        if (query.get("format") or [""])[0] == "json":
            self._send(200, "application/json", json.dumps(data, indent=2).encode())
        else:
            self._send(200, "text/html; charset=utf-8", _render_html(data).encode())


def run(port: int | None = None, host: str | None = None) -> None:
    bind_host = host or dashboard_module.host()
    bind_port = port or dashboard_module.port()
    server = ThreadingHTTPServer((bind_host, bind_port), _Handler)
    print(f"rbridge serve → http://{bind_host}:{bind_port}/  (token required)")
    print(f"live URL: {dashboard_module.url()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
