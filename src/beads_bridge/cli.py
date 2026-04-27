"""CLI for beads-bridge."""

import sys

from . import api as api_module
from . import beads as beads_module
from . import body as body_module
from . import config as config_module
from . import daemon as daemon_module
from . import projects_list as projects_list_module
from . import projects as projects_module
from . import reminders as reminders_module
from . import settings as settings_module
from . import state as state_module


USAGE = "Usage: bbridge [run|sync|doctor|status|lint|probe]"


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
    else:
        print(USAGE)
        sys.exit(1)


def sync_once() -> None:
    cfg = config_module.load()
    state = state_module.load(cfg.state_path)
    count = daemon_module.sync_once(cfg, state)
    print(f"Synced {count} project(s).")


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
            issues = {i.id: i for i in beads_module.list_issues(p.path, cfg.statuses)}
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
