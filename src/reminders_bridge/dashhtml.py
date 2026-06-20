"""Render dashboard view dicts as minimal HTML with clickable drill-down links.

For a human in a browser (`?format=html` or `?html`). Agents use the default
markdown / `?format=json`. Every internal link carries the full incoming query
string (`qs`, e.g. `?t=…&html`) so navigation keeps the token *and* the chosen
format/view.
"""

import html
from typing import Any
from urllib.parse import quote


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _href(path: str, label: str, qs: str) -> str:
    return f'<a href="{_esc(path + qs)}">{_esc(label)}</a>'


def _counts(counts: dict[str, int]) -> str:
    return _esc(" ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "—")


_STYLE = (
    "body{font:13px/1.5 ui-monospace,Menlo,monospace;margin:1.5rem;max-width:70rem}"
    "h1{font-size:1.1rem}h2{font-size:.95rem;margin-top:1.4rem}"
    "table{border-collapse:collapse;width:100%}"
    "td,th{text-align:left;padding:.2rem .6rem;border-bottom:1px solid #ddd}"
    "th{border-bottom:2px solid #999}a{color:#06c}.err{color:#b00}"
    "pre{background:#f6f6f6;padding:.7rem;overflow:auto}.meta{color:#888}"
    "nav{margin:.6rem 0}nav a{margin-right:.8rem}"
)


def _nav(qs: str) -> str:
    items = [
        ("/", "overview"), ("/sessions", "sessions"), ("/tabs", "tabs"),
        ("/voice", "voice"), ("/activity", "activity"),
    ]
    return "<nav>" + " · ".join(_href(p, label, qs) for p, label in items) + "</nav>"


def _page(title: str, qs: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset=utf-8><title>{_esc(title)}</title>"
        f"<style>{_STYLE}</style></head><body>{_nav(qs)}{body}</body></html>"
    )


def _activity_table(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "<p>(none)</p>"
    rows = "".join(
        f"<tr><td>{_esc(e['ts'])}</td><td>{_esc(e['project'])}</td>"
        f"<td>{_esc(e['kind'])}</td><td>{_esc(e.get('bead_id') or '-')}</td>"
        f"<td>{_esc(e['detail'])}</td></tr>"
        for e in entries
    )
    return (
        "<table><tr><th>time</th><th>list/project</th><th>kind</th>"
        f"<th>bead</th><th>detail</th></tr>{rows}</table>"
    )


def overview(d: dict[str, Any], qs: str) -> str:
    cfg = d["config"]
    t = d["totals"]
    project_rows = []
    for p in d["projects"]:
        name = _href(f"/project/{quote(p['name'])}", p["name"], qs)
        if p["error"]:
            project_rows.append(f"<tr><td>{name}</td><td colspan=3 class=err>"
                                f"{_esc(p['error'][:200])}</td></tr>")
        else:
            project_rows.append(
                f"<tr><td>{name}</td><td>{p['total']}</td>"
                f"<td>{_counts(p['counts'])}</td><td>{p['linked']}</td></tr>"
            )
    body = (
        f"<h1>rbridge — at a glance</h1>"
        f"<p class=meta>{_esc(d['generated_at'])} · poll {cfg['poll_interval_s']}s · "
        f"statuses {_esc(','.join(cfg['statuses']))}</p>"
        f"<p>projects {t['projects']} · beads {_counts(t['beads'])} · "
        f"sessions {t['sessions_pending']} pending · tabs {t['tabs']} · "
        f"voice {t['voice']}</p>"
        "<h2>projects</h2><table><tr><th>project</th><th>beads</th>"
        "<th>by status</th><th>linked</th></tr>"
        f"{''.join(project_rows) or '<tr><td>(none)</td></tr>'}</table>"
        f"<h2>recent activity</h2>{_activity_table(d['activity'])}"
    )
    return _page("rbridge", qs, body)


def project(d: dict[str, Any], qs: str) -> str:
    rows = "".join(
        f"<tr><td>{_esc(b['id'])}</td><td>p{b['priority']}</td>"
        f"<td>{_esc(b['status'])}</td><td>{_esc(b['type'])}</td>"
        f"<td>{'✓' if b['linked'] else ''}</td><td>{_esc(b['title'])}</td></tr>"
        for b in d["beads"]
    )
    err = f"<p class=err>{_esc(d['error'])}</p>" if d["error"] else ""
    body = (
        f"<h1>{_esc(d['name'])}</h1>"
        f"<p class=meta>{_esc(d['path'])} · {_esc(d['list_name'])} · "
        f"{_counts(d['counts'])}</p>{err}"
        "<table><tr><th>id</th><th>pri</th><th>status</th><th>type</th>"
        f"<th>linked</th><th>title</th></tr>{rows or '<tr><td>(none)</td></tr>'}</table>"
    )
    return _page(d["name"], qs, body)


def sessions(d: dict[str, Any], qs: str) -> str:
    rows = "".join(
        f"<tr><td>{_esc(s['engine'])}</td>"
        f"<td>{'done' if s['completed'] else 'pending'}</td>"
        f"<td>{_esc(s['mode'])}</td><td>{_esc(s['title'])}</td></tr>"
        for s in d["sessions"]
    )
    body = (
        f"<h1>sessions</h1><p class=meta>{_esc(d['generated_at'])}</p>"
        "<table><tr><th>engine</th><th>state</th><th>mode</th><th>title</th></tr>"
        f"{rows or '<tr><td>(none)</td></tr>'}</table>"
    )
    return _page("sessions", qs, body)


def tabs(d: dict[str, Any], qs: str) -> str:
    rows = "".join(
        f"<tr><td>{t['pid']}</td><td>{_esc(t['tty'])}</td><td>{_esc(t['mode'])}</td>"
        f"<td>{_esc(t['session'] or '-')}</td><td>{_esc(t['title'] or t['cwd'])}</td></tr>"
        for t in d["tabs"]
    )
    body = (
        f"<h1>claude tabs</h1><p class=meta>{_esc(d['generated_at'])}</p>"
        "<table><tr><th>pid</th><th>tty</th><th>mode</th><th>session</th>"
        f"<th>title/cwd</th></tr>{rows or '<tr><td>(none live)</td></tr>'}</table>"
    )
    return _page("tabs", qs, body)


def voice(d: dict[str, Any], qs: str) -> str:
    rows = "".join(
        f"<tr><td>{_esc(m['slug'])}</td><td>{_esc(m['kind'])}</td>"
        f"<td>{_esc(m['created_at'])}</td><td>{_esc(m['root'] or '—')}</td></tr>"
        for m in d["mailboxes"]
    )
    body = (
        f"<h1>voice exchanges</h1><p class=meta>{_esc(d['generated_at'])}</p>"
        "<table><tr><th>slug</th><th>kind</th><th>created</th><th>root</th></tr>"
        f"{rows or '<tr><td>(none active)</td></tr>'}</table>"
    )
    return _page("voice", qs, body)


def activity(d: dict[str, Any], qs: str) -> str:
    body = f"<h1>activity</h1>{_activity_table(d['activity'])}"
    return _page("activity", qs, body)


RENDER = {
    "overview": overview, "project": project, "sessions": sessions,
    "tabs": tabs, "voice": voice, "activity": activity,
}
