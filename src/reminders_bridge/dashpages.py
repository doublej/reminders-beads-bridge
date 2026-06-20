"""Render dashboard view dicts (snapshot.py) as compact markdown.

Markdown, not HTML: the primary reader is an agent fetching the URL, so the
output is dense and chrome-free — sections, one line per row, drill-down paths
stated once with the token. JSON (`?format=json`) carries the same data for
structured reads.
"""

from typing import Any


def _counts(counts: dict[str, int]) -> str:
    return " ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "—"


def _nav(token: str) -> str:
    return (
        f"## nav — append `?t={token}` to any path\n"
        "`/` overview · `/project/<name>` · `/sessions` · `/tabs` · "
        "`/voice` · `/activity` · add `&format=json` for structured data"
    )


def _activity(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "(none)"
    return "\n".join(
        f"{e['ts'][5:16]} {e['project']:<20.20} {e['kind']:<9.9} "
        f"{(e.get('bead_id') or '-'):<9.9} {e['detail']}"
        for e in entries
    )


def overview(d: dict[str, Any], token: str) -> str:
    cfg = d["config"]
    rows = []
    for p in d["projects"]:
        if p["error"]:
            rows.append(f"{p['name']} · ERROR: {p['error']}")
        else:
            rows.append(
                f"{p['name']} · total {p['total']} linked {p['linked']} · "
                f"{_counts(p['counts'])}"
            )
    t = d["totals"]
    return "\n".join([
        f"# rbridge @ {d['generated_at']}",
        f"poll {cfg['poll_interval_s']}s · statuses {','.join(cfg['statuses'])}",
        "",
        "## totals",
        f"projects {t['projects']} · beads {_counts(t['beads'])} · "
        f"sessions {t['sessions_pending']} pending · tabs {t['tabs']} · "
        f"voice {t['voice']}",
        "",
        "## projects",
        "\n".join(rows) or "(none)",
        "",
        _nav(token),
        "",
        "## recent activity (20)",
        _activity(d["activity"]),
    ])


def project(d: dict[str, Any], token: str) -> str:
    head = [
        f"# {d['name']} @ {d['generated_at']}",
        f"path {d['path']} · list {d['list_name']}",
    ]
    if d["error"]:
        head.append(f"ERROR: {d['error']}")
    head.append(f"counts: {_counts(d['counts'])}")
    rows = [
        f"{b['id']} p{b['priority']} {b['status']:<12.12} {b['type']:<7.7} "
        f"{'L' if b['linked'] else ' '} {b['title']}"
        for b in d["beads"]
    ]
    return "\n".join([
        *head,
        "",
        "## beads (id · pNN · status · type · L=linked · title)",
        "\n".join(rows) or "(none)",
        "",
        _nav(token),
    ])


def sessions(d: dict[str, Any], token: str) -> str:
    rows = [
        f"[{s['engine']}] {'done' if s['completed'] else 'pending'} "
        f"{s['mode']:<11.11} {s['title']}"
        for s in d["sessions"]
    ]
    return "\n".join([
        f"# sessions @ {d['generated_at']}",
        "",
        "## (engine · state · mode · title)",
        "\n".join(rows) or "(none)",
        "",
        _nav(token),
    ])


def tabs(d: dict[str, Any], token: str) -> str:
    rows = [
        f"pid {t['pid']:<7} {t['tty']:<8.8} {t['mode']:<7.7} "
        f"sid {t['session'] or '-':<8} {t['title'] or t['cwd']}"
        for t in d["tabs"]
    ]
    return "\n".join([
        f"# claude tabs @ {d['generated_at']}",
        "",
        "## (pid · tty · mode · session · title/cwd)",
        "\n".join(rows) or "(none live)",
        "",
        _nav(token),
    ])


def voice(d: dict[str, Any], token: str) -> str:
    rows = [
        f"{m['slug']:<28.28} {m['kind']:<13.13} {m['created_at']:<20.20} "
        f"{m['root'] or '—'}"
        for m in d["mailboxes"]
    ]
    return "\n".join([
        f"# voice exchanges @ {d['generated_at']}",
        "",
        "## (slug · kind · created · root)",
        "\n".join(rows) or "(none active)",
        "",
        _nav(token),
    ])


def activity(d: dict[str, Any], token: str) -> str:
    return "\n".join([
        f"# activity @ {d['generated_at']}",
        "",
        _activity(d["activity"]),
        "",
        _nav(token),
    ])
