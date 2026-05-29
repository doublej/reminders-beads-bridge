"""CLI for reminders-bridge."""

import argparse
import json
import os
import sys

from . import api as api_module
from . import beads as beads_module
from . import body as body_module
from . import config as config_module
from . import daemon as daemon_module
from . import mailbox as mailbox_module
from . import navigation as navigation_module
from . import projects_list as projects_list_module
from . import projects as projects_module
from . import reminders as reminders_module
from . import settings as settings_module
from . import state as state_module
from . import tabs as tabs_module


USAGE = "Usage: rbridge [run|sync|doctor|status|lint|probe|mailbox|tabs]"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run":
        daemon_module.run()
    elif cmd == "sync":
        sync_once()
    elif cmd == "doctor":
        doctor()
    elif cmd == "status":
        status()
    elif cmd == "lint":
        lint()
    elif cmd == "probe":
        from . import probe as probe_module
        probe_module.run()
    elif cmd == "mailbox":
        mailbox_cli(sys.argv[2:])
    elif cmd == "tabs":
        tabs()
    else:
        print(USAGE)
        sys.exit(1)


def sync_once() -> None:
    cfg = config_module.load()
    state = state_module.load(cfg.state_path)
    count = daemon_module.sync_once(cfg, state)
    print(f"Synced {count} project(s).")


def tabs() -> None:
    from . import ghostty as ghostty_module
    from . import transcript as transcript_module

    discovered = ghostty_module.discover()
    print(f"Tabs list: {tabs_module.list_name()!r}")
    print(f"Live Ghostty tabs running Claude Code: {len(discovered)}")
    for t in discovered:
        s = transcript_module.resolve_session(t.cwd)
        sid = s.session_id[:8] if s else "-"
        print(f"  pid={t.pid:<7} {t.tty:<8} {t.mode:<7} sid={sid:<8} {t.project}")


def status() -> None:
    cfg = config_module.load()
    state = state_module.load(cfg.state_path)
    all_projects = projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
    active = projects_module.filter_existing(all_projects)
    try:
        hidden = projects_list_module.sync(cfg.list_prefix, active)
    except RuntimeError as e:
        print(f"(master list unavailable: {e})")
        hidden = set()
    try:
        settings_values = settings_module.sync(cfg.list_prefix)
    except RuntimeError as e:
        print(f"(settings list unavailable: {e})")
        settings_values = settings_module.defaults()
    print(f"Registry: {cfg.registry_path}")
    print(f"Master list: {projects_list_module.list_name(cfg.list_prefix)!r}")
    print(f"Settings list: {settings_module.list_name(cfg.list_prefix)!r}")
    for key, val in settings_values.items():
        print(f"  {key} = {val}")
    print(
        f"Projects: {len(all_projects)} total, {len(active)} with .beads, "
        f"{len(hidden)} hidden, {len(active) - len(hidden)} visible"
    )
    for p in active:
        ps = state.projects.get(str(p.path))
        linked = len(ps.links) if ps else 0
        flag = "hidden" if p.name in hidden else "visible"
        print(
            f"  [{flag:<7}] {p.name:<30}  "
            f"list={p.list_name!r:<40}  linked={linked}"
        )


def lint() -> None:
    cfg = config_module.load()
    projects = projects_module.filter_existing(
        projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
    )
    total = 0
    for p in projects:
        try:
            issues = {i.id: i for i in beads_module.list_issues(p.path)}
        except RuntimeError as e:
            print(f"  {p.name}: bd error — {e}")
            continue
        reminders = reminders_module.list_reminders(p.list_name)
        project_problems: list[str] = []
        for rem in reminders:
            bead_id = rem.name.split(":", 1)[0] if ":" in rem.name else None
            issue = issues.get(bead_id) if bead_id else None
            if bead_id and issue is None:
                project_problems.append(f"    orphan: {rem.name!r}")
                continue
            for li in body_module.lint(rem.body, issue):
                project_problems.append(f"    {rem.name!r}: [{li.code}] {li.message}")
        if project_problems:
            print(f"{p.name} ({len(project_problems)} issue{'s' if len(project_problems) != 1 else ''}):")
            for line in project_problems:
                print(line)
            total += len(project_problems)
    if total == 0:
        print("All reminders clean.")
    else:
        print(f"\n{total} issue(s) found.")
        sys.exit(1)


def doctor() -> None:
    cfg = config_module.load()
    print("Config:")
    print(f"  registry:   {cfg.registry_path}")
    print(f"  state:      {cfg.state_path}")
    print(f"  poll:       {cfg.poll_interval_s}s")
    print(f"  prefix:     {cfg.list_prefix!r}")
    print(f"  statuses:   {cfg.statuses}")
    print(f"  api_url:    {cfg.api_url}")

    print("\nbd CLI:")
    projects = projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
    active = projects_module.filter_existing(projects)
    if not active:
        print("  no active project — cannot verify bd")
        sys.exit(1)
    try:
        version = beads_module.doctor(active[0].path)
        print(f"  ok — {version}")
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    print("\nReminders permission:")
    probe = f"{cfg.list_prefix}__doctor__"
    try:
        reminders_module.create_list(probe)
        reminders_module.list_reminders(probe)
        reminders_module.delete_list(probe)
        print(f"  ok — probe list {probe!r} created and removed")
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    print(f"\nRegistry: {len(projects)} entries, {len(active)} with .beads/")

    print("\nbeads-kanban API:")
    client = api_module.Client(base_url=cfg.api_url, timeout_s=cfg.api_timeout_s)
    try:
        cwd = client.cwd_get()
        healthy = client.agent_health()
        print(f"  ok — cwd={cwd.get('cwd')!r} agent_healthy={healthy}")
    except api_module.APIError as e:
        print(f"  unreachable ({e.code}) — plumbing-only, not required for sync")

    boxes = mailbox_module.list_active()
    nav = "ENABLED" if navigation_module.sandbox.nav_enabled() else "DISABLED (RBRIDGE_VOICE_NAV)"
    print(f"\nVoice mailboxes: {len(boxes)} active — file-nav {nav}")
    for mb in boxes:
        on = "on" if navigation_module.is_active(mb) else "off"
        print(f"  {mb.slug:<30}  kind={mb.kind}  nav={on}  root={mb.source_cwd or '—'}")

    from . import ghostty as ghostty_module
    n_tabs = len(ghostty_module.discover())
    print(f"\nGhostty Claude tabs: {n_tabs} live → list {tabs_module.list_name()!r}")


def _read_brief(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return open(arg).read()


def mailbox_cli(args: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="rbridge mailbox")
    sub = parser.add_subparsers(dest="action", required=True)
    p_open = sub.add_parser("open", help="open or refresh a voice mailbox")
    p_open.add_argument("--slug", required=True)
    p_open.add_argument(
        "--kind", default="REMINDERS", choices=["REMINDERS", "CLAUDE_VOICE"]
    )
    p_open.add_argument(
        "--brief", default="-",
        help="path to brief markdown, or '-' for stdin (default)",
    )
    p_open.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="repo root for file-navigation; defaults to the current directory",
    )
    p_read = sub.add_parser("read", help="drain user responses as JSON")
    p_read.add_argument("--slug", required=True)
    p_close = sub.add_parser("close", help="tear down a voice mailbox")
    p_close.add_argument("--slug", required=True)
    p_refresh = sub.add_parser("refresh", help="re-up mailbox + mirror reminders")
    p_refresh.add_argument("--slug", required=True)
    sub.add_parser("list", help="enumerate active mailboxes")
    ns = parser.parse_args(args)

    if ns.action == "open":
        _mailbox_open(ns)
    elif ns.action == "read":
        _mailbox_read(ns)
    elif ns.action == "close":
        _mailbox_close(ns)
    elif ns.action == "refresh":
        _mailbox_refresh(ns)
    elif ns.action == "list":
        _mailbox_list()


def _mailbox_open(ns) -> None:
    brief_text = _read_brief(ns.brief)
    if not brief_text.strip():
        print("error: brief is empty", file=sys.stderr)
        sys.exit(1)
    try:
        mb = mailbox_module.open_mailbox(
            slug=ns.slug, kind=ns.kind, brief_text=brief_text,
            source_cwd=ns.cwd or "",
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"error: Reminders unavailable — {e}", file=sys.stderr)
        print(f"brief saved to: {mailbox_module._brief_path(ns.slug)}", file=sys.stderr)
        sys.exit(2)
    print(f"mailbox opened: {mb.slug}")
    print(f"list:    {mb.list_name}")
    print(f"brief:   {mb.brief_path}")
    print(f"read:    rbridge mailbox read --slug {mb.slug}")
    print(f"close:   rbridge mailbox close --slug {mb.slug}")


def _mailbox_read(ns) -> None:
    try:
        out = mailbox_module.read(ns.slug)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if out["has_done"]:
        print(
            "note: a `done` reminder is present — daemon will close on next "
            "cycle. Consume responses now.",
            file=sys.stderr,
        )
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _mailbox_close(ns) -> None:
    result = mailbox_module.close(ns.slug, reason="cli")
    if not result.found:
        print(f"no mailbox for slug {ns.slug!r}", file=sys.stderr)
        sys.exit(1)
    parts: list[str] = []
    if result.list_deleted:
        parts.append("list deleted")
    elif result.list_was_missing:
        parts.append("list was already missing")
    elif result.list_error:
        parts.append(f"list delete FAILED ({result.list_error})")
    if result.mirror_error:
        parts.append(f"mirror delete failed ({result.mirror_error})")
    parts.append("state cleared")
    print(f"mailbox closed: {ns.slug} — " + ", ".join(parts))
    if result.list_error:
        sys.exit(2)


def _mailbox_refresh(ns) -> None:
    if mailbox_module.refresh(ns.slug):
        print(f"refreshed: {ns.slug}")
    else:
        print(f"no mailbox for slug {ns.slug!r}", file=sys.stderr)
        sys.exit(1)


def _mailbox_list() -> None:
    boxes = mailbox_module.list_active()
    if not boxes:
        print("(no active mailboxes)")
        return
    for mb in boxes:
        print(
            f"{mb.slug:<30}  kind={mb.kind:<14}  "
            f"created={mb.created_at}  list={mb.list_name!r}"
        )
