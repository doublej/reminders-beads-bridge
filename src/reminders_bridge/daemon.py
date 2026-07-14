"""Poll loop that reconciles beads issues with Apple Reminders."""

import logging
import os
import sys
import time
from typing import Any

from . import activity as activity_module
from . import agent_marker as agent_marker_module
from . import api as api_module
from . import beads as beads_module
from . import body as body_module
from . import captures as captures_module
from . import commands as commands_module
from . import dashboard as dashboard_module
from . import sessions as sessions_module
from . import config as config_module
from . import fixer as fixer_module
from . import heartbeat as heartbeat_module
from . import link as link_module
from . import mailbox as mailbox_module
from . import migrate as migrate_module
from . import projects_list as projects_list_module
from . import readme as readme_module
from . import projects as projects_module
from . import reminders as reminders_module
from . import serverctl as serverctl_module
from . import settings as settings_module
from . import state as state_module
from . import tabs as tabs_module
from . import triggers as triggers_module
from . import watcher as watcher_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def _capture_unprefixed(
    project: projects_module.Project,
    ps: state_module.ProjectState,
    remote_list: list[reminders_module.Reminder],
    remote_by_bead: dict[str, list[reminders_module.Reminder]],
    issues: list[beads_module.Issue],
) -> bool:
    linked_reminder_ids = {lk.reminder_id for lk in ps.links.values()}
    valid_ids = {i.id for i in issues}
    captured_any = False
    for rem in remote_list:
        if ":" in rem.name and rem.name.split(":", 1)[0].strip() in valid_ids:
            continue
        if rem.completed or rem.id in linked_reminder_ids:
            continue
        title = rem.name.strip()
        if not title:
            continue
        try:
            new_issue = beads_module.create_issue(
                project.path, title=title, description=rem.body, priority=2
            )
        except RuntimeError as e:
            log.warning("Capture failed for %r in %s: %s", title, project.name, e)
            continue
        issues.append(new_issue)
        ps.links[new_issue.id] = state_module.Link(
            reminder_id=rem.id,
            bead_status=new_issue.status,
            reminder_completed=False,
        )
        remote_by_bead.setdefault(new_issue.id, []).append(rem)
        activity_module.record(project.name, "captured", new_issue.id, title)
        log.info("Captured reminder → %s: %s", new_issue.id, title)
        captured_any = True
    return captured_any


def _adopt_or_dedup(
    issue: beads_module.Issue,
    ps: state_module.ProjectState,
    remote_by_bead: dict[str, list[reminders_module.Reminder]],
    used_ids: set[str],
    batch: reminders_module.Batch,
) -> state_module.Link | None:
    candidates = [
        r for r in remote_by_bead.get(issue.id, []) if r.id not in used_ids
    ]
    if not candidates:
        return None
    adopted = candidates[0]
    link = state_module.Link(
        reminder_id=adopted.id,
        bead_status=issue.status,
        reminder_completed=False,
    )
    ps.links[issue.id] = link
    for extra in candidates[1:]:
        if extra.id not in used_ids:
            batch.deletes.append(extra.id)
            used_ids.add(extra.id)
            log.info("Dedup: delete duplicate reminder for %s", issue.id)
    return link


def _diff_existing(
    issue: beads_module.Issue,
    link: state_module.Link,
    rem: reminders_module.Reminder,
    remote_by_bead: dict[str, list[reminders_module.Reminder]],
    used_ids: set[str],
    project: projects_module.Project,
    client: api_module.Client,
    batch: reminders_module.Batch,
    closes: list[str],
    reopens: list[str],
) -> None:
    used_ids.add(rem.id)
    for dup in remote_by_bead.get(issue.id, []):
        if dup.id != rem.id and dup.id not in used_ids:
            batch.deletes.append(dup.id)
            used_ids.add(dup.id)
            log.info("Dedup: delete duplicate reminder for %s", issue.id)

    if rem.completed and not link.reminder_completed and issue.status != "closed":
        closes.append(issue.id)
        return
    if (not rem.completed) and link.reminder_completed and issue.status == "closed":
        reopens.append(issue.id)
        return

    target_completed = issue.status == "closed"
    current_body = body_module.consume_agent_markers(
        rem.body,
        lambda args: agent_marker_module.dispatch(client, project, issue, args),
    )
    expected_body = body_module.compose(issue, current_body)
    if expected_body != rem.body and "<bb:restored" in expected_body:
        activity_module.record(project.name, "restored", issue.id, "tamper detected")
    if link.bead_status and link.bead_status != issue.status:
        activity_module.record(
            project.name, "status", issue.id, f"{link.bead_status} → {issue.status}"
        )
    expected_title = link_module.bead_title(issue)
    expected_priority = link_module.bead_priority(issue)
    patch: dict = {"id": rem.id}
    if rem.name != expected_title:
        patch["name"] = expected_title
    if rem.body != expected_body:
        patch["body"] = expected_body
    if rem.completed != target_completed:
        patch["completed"] = target_completed
    if rem.priority != expected_priority:
        patch["priority"] = expected_priority
    if len(patch) > 1:
        batch.updates.append(patch)
    link.bead_status = issue.status
    link.reminder_completed = target_completed


def _prune_orphans(
    project: projects_module.Project,
    ps: state_module.ProjectState,
    issues_by_id: dict[str, beads_module.Issue],
    remote_by_id: dict[str, reminders_module.Reminder],
    used_ids: set[str],
    batch: reminders_module.Batch,
) -> None:
    for bid in list(ps.links):
        if bid in issues_by_id:
            continue
        link = ps.links[bid]
        if link.reminder_id in remote_by_id and link.reminder_id not in used_ids:
            batch.deletes.append(link.reminder_id)
            used_ids.add(link.reminder_id)
            log.info("Prune reminder for deleted bead %s", bid)
            activity_module.record(project.name, "pruned", bid, "bead no longer listed")
        del ps.links[bid]


def _commit_batch(
    project: projects_module.Project,
    ps: state_module.ProjectState,
    issues_by_id: dict[str, beads_module.Issue],
    batch: reminders_module.Batch,
    create_bead_ids: list[str],
) -> bool:
    if batch.empty():
        return True
    try:
        new_ids = reminders_module.apply_batch(project.list_name, batch)
    except RuntimeError as e:
        log.error("Batch failed for %s: %s", project.name, e)
        return False
    for bid, rid in zip(create_bead_ids, new_ids):
        issue = issues_by_id[bid]
        ps.links[bid] = state_module.Link(
            reminder_id=rid,
            bead_status=issue.status,
            reminder_completed=issue.status == "closed",
        )
        activity_module.record(project.name, "created", bid, issue.title)
    log.info(
        "%s: +%d new, %d updated, %d deleted",
        project.name,
        len(batch.creates),
        len(batch.updates),
        len(batch.deletes),
    )
    return True


def _apply_signals(
    project: projects_module.Project,
    ps: state_module.ProjectState,
    closes: list[str],
    reopens: list[str],
) -> None:
    for bid in closes:
        try:
            beads_module.close_issue(project.path, bid)
        except RuntimeError as e:
            log.warning("Close failed %s: %s", bid, e)
            continue
        link = ps.links.get(bid)
        if link:
            link.bead_status = "closed"
            link.reminder_completed = True
        log.info("Closed bead %s (reminder completed)", bid)
        activity_module.record(project.name, "closed", bid, "via reminder completion")
    for bid in reopens:
        try:
            beads_module.reopen_issue(project.path, bid)
        except RuntimeError as e:
            log.warning("Reopen failed %s: %s", bid, e)
            continue
        link = ps.links.get(bid)
        if link:
            link.bead_status = "open"
            link.reminder_completed = False
        log.info("Reopened bead %s (reminder unchecked)", bid)
        activity_module.record(project.name, "reopened", bid, "via reminder uncheck")


def _prune_closed(
    issue: beads_module.Issue,
    ps: state_module.ProjectState,
    remote_by_id: dict[str, reminders_module.Reminder],
    used_ids: set[str],
    batch: reminders_module.Batch,
    project: projects_module.Project,
) -> None:
    link = ps.links.get(issue.id)
    if (
        link
        and link.reminder_id in remote_by_id
        and link.reminder_id not in used_ids
    ):
        batch.deletes.append(link.reminder_id)
        used_ids.add(link.reminder_id)
        activity_module.record(
            project.name, "pruned", issue.id, "closed; show_completed off"
        )
    ps.links.pop(issue.id, None)


def reconcile_project(
    project: projects_module.Project,
    cfg: config_module.Config,
    state: state_module.State,
    client: api_module.Client,
    *,
    show_completed: bool = False,
) -> None:
    try:
        issues = beads_module.list_issues(project.path)
    except RuntimeError as e:
        log.warning("Skip %s: %s", project.name, e)
        return

    reminders_module.create_list(project.list_name)
    remote_list = reminders_module.list_reminders(project.list_name)
    remote_by_id = {r.id: r for r in remote_list}
    remote_by_bead = link_module.index_by_bead_id(remote_list)

    ps = state.projects.get(str(project.path))
    if ps is None:
        ps = state_module.ProjectState(list_name=project.list_name)
        state.projects[str(project.path)] = ps
    ps.list_name = project.list_name

    if _capture_unprefixed(project, ps, remote_list, remote_by_bead, issues):
        state_module.save(cfg.state_path, state)

    issues_by_id = {i.id: i for i in issues}
    batch = reminders_module.Batch()
    create_bead_ids: list[str] = []
    closes: list[str] = []
    reopens: list[str] = []
    used_ids: set[str] = set()

    for issue in issues:
        is_closed = issue.status == "closed"
        if is_closed and not show_completed:
            _prune_closed(issue, ps, remote_by_id, used_ids, batch, project)
            continue
        syncable = issue.status in cfg.statuses or (is_closed and show_completed)
        link = ps.links.get(issue.id)
        if link and link.reminder_id not in remote_by_id:
            link = None
            ps.links.pop(issue.id, None)
        if link is None:
            link = _adopt_or_dedup(issue, ps, remote_by_bead, used_ids, batch)
        if link and link.reminder_id in remote_by_id:
            _diff_existing(
                issue, link, remote_by_id[link.reminder_id], remote_by_bead,
                used_ids, project, client, batch, closes, reopens,
            )
        elif syncable:
            batch.creates.append({
                "name": link_module.bead_title(issue),
                "body": body_module.compose(issue),
                "priority": link_module.bead_priority(issue),
                "completed": is_closed,
            })
            create_bead_ids.append(issue.id)

    _prune_orphans(project, ps, issues_by_id, remote_by_id, used_ids, batch)
    if not _commit_batch(project, ps, issues_by_id, batch, create_bead_ids):
        return

    state_module.save(cfg.state_path, state)
    _apply_signals(project, ps, closes, reopens)
    if closes or reopens:
        state_module.save(cfg.state_path, state)


_FAIL_THRESHOLD = int(os.getenv("RBRIDGE_FIXER_THRESHOLD", "5"))
_fail_counts: dict[str, int] = {}
_fail_messages: dict[str, str] = {}


def _safe(name: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
    except Exception as e:
        heartbeat_module.fail(name, str(e))
        _fail_counts[name] = _fail_counts.get(name, 0) + 1
        _fail_messages[name] = str(e)
        log.warning(
            "%s failed (%d/%d): %s", name, _fail_counts[name], _FAIL_THRESHOLD, e
        )
        if _fail_counts[name] >= _FAIL_THRESHOLD:
            errors = [
                f"{n} (x{c}): {_fail_messages[n]}"
                for n, c in _fail_counts.items()
            ]
            list_name = os.getenv("RBRIDGE_CLAUDE_LIST", "_rb_claude_sessions")
            if fixer_module.trigger_auto(errors, list_name):
                escalated = [n for n, c in _fail_counts.items() if c >= _FAIL_THRESHOLD]
                for n in escalated:
                    _fail_counts.pop(n, None)
                    _fail_messages.pop(n, None)
        return None
    heartbeat_module.ok(name)
    _fail_counts.pop(name, None)
    _fail_messages.pop(name, None)
    return result


def _run_activity() -> None:
    activity_module.sync()
    activity_module.prune()


def _run_triggers() -> None:
    n = triggers_module.process_all()
    if n:
        log.info("Launched %d session(s) from triggers lists", n)


def _restart() -> None:
    log.info("Restart requested via Settings — re-executing %s", sys.argv)
    activity_module.record(settings_module.list_name(), "restarted", "", "via settings")
    serverctl_module.ensure(False)  # reap the serve child so the new daemon can re-bind
    os.execv(sys.argv[0], sys.argv)


def _apply_controls(cfg: config_module.Config, settings: dict) -> None:
    poll_ms = settings.get("poll_ms")
    if isinstance(poll_ms, int) and poll_ms > 0:
        new_s = poll_ms / 1000.0
        if abs(new_s - cfg.poll_interval_s) > 1e-9:
            log.info("Poll interval set via Settings: %.3fs → %.3fs", cfg.poll_interval_s, new_s)
            cfg.poll_interval_s = new_s
    _safe("Dashboard server lifecycle", serverctl_module.ensure, bool(settings.get("dashboard", False)))
    if settings.get("restart"):
        _restart()


# Idle-tick throttle. On an EventKit-change wakeup (woke=True) every lane runs
# regardless — Reminders edits (toggles, tab `send:`, voice `fetch:`, completing
# a task) stay instant. These intervals only throttle *pure-interval* idle ticks,
# where nothing in Reminders changed: a lane whose sole non-Reminders trigger is a
# subprocess exit, a new Ghostty tab, or a `bd` edit tolerates this latency. This
# is what keeps idle CPU low even when poll_ms is small — without it the full
# pipeline (incl. the ~280ms Ghostty `ps` scan) reran every poll.
_LANE_EVERY_S: dict[str, float] = {
    "migrate": 120.0,
    "projects_list": 30.0,
    "settings": 30.0,
    "readme": 60.0,
    "dashboard": 60.0,
    "activity": 30.0,
    "captures": 30.0,
    "sessions": 30.0,
    "tabs": 60.0,
    "triggers": 30.0,
    "mailbox": 60.0,
    "commands": 15.0,
    "reconcile": 10.0,
}
_lane_last: dict[str, float] = {}
_cache: dict[str, Any] = {"hidden": set(), "settings": None}
_MIN_WAIT_S = float(os.getenv("RBRIDGE_MIN_WAIT_S", "3.0"))


def _due(name: str, now: float, woke: bool) -> bool:
    if woke or (now - _lane_last.get(name, 0.0)) >= _LANE_EVERY_S[name]:
        _lane_last[name] = now
        return True
    return False


def sync_once(
    cfg: config_module.Config, state: state_module.State, woke: bool = False
) -> int:
    now = time.monotonic()
    with reminders_module.autorelease_pool():
        all_projects = projects_module.load_projects(cfg.registry_path, cfg.list_prefix)
        active = projects_module.filter_existing(all_projects)
        if _due("migrate", now, woke):
            _safe("List migration", migrate_module.run, cfg.list_prefix, active)
        projects_due = _due("projects_list", now, woke)
        if projects_due:
            hidden = _safe(
                "Projects list sync", projects_list_module.sync, cfg.list_prefix, active
            )
            if hidden is not None:
                _cache["hidden"] = hidden
        hidden = _cache["hidden"]
        if _cache["settings"] is None or _due("settings", now, woke):
            settings = _safe("Settings list sync", settings_module.sync)
            if settings is None:
                settings = settings_module.defaults()
            _cache["settings"] = settings
        settings = _cache["settings"]
        _apply_controls(cfg, settings)
        visible = [p for p in active if p.name not in hidden]
        log.info(
            "Registry: %d projects (%d with .beads, %d hidden, %d visible) | settings=%s",
            len(all_projects),
            len(active),
            len(hidden),
            len(visible),
            settings,
        )
        client = api_module.Client(base_url=cfg.api_url, timeout_s=cfg.api_timeout_s)
        if _due("readme", now, woke):
            _safe("Readme list sync", readme_module.sync)
        if _due("dashboard", now, woke):
            _safe("Dashboard list sync", dashboard_module.sync)
        if _due("activity", now, woke):
            _safe("Activity list sync", _run_activity)
        if _due("captures", now, woke):
            _safe("Capture poll", captures_module.poll)
        if _due("sessions", now, woke):
            _safe("Sessions poll", sessions_module.poll)
        if _due("tabs", now, woke):
            _safe("Tabs sync", tabs_module.sync)
        if _due("triggers", now, woke):
            _safe("Trigger lists sync", _run_triggers)
        if _due("mailbox", now, woke):
            _safe("Mailbox sync", mailbox_module.sync)
        if _due("commands", now, woke):
            _safe("Commands", commands_module.sync, visible)
        if projects_due:
            _safe(
                "Apply hides", projects_list_module.apply_hides,
                active, hidden, state, cfg.state_path,
            )
        if _due("reconcile", now, woke):
            show_completed = settings.get("show_completed", False)
            _safe(
                "Reconcile", _run_reconcile, visible, cfg, state, client, show_completed
            )
        heartbeat_module.persist()
        reminders_module.reset_store()
        return len(visible)


def _run_reconcile(visible, cfg, state, client, show_completed: bool) -> None:
    """Reconcile every visible project, resilient per-project — one project's
    unexpected error no longer aborts the rest of the cycle (a single bd failure
    silently killed all reconciles for two weeks). Re-raise a summary so `_safe`
    records the failure + escalates."""
    errs = []
    for project in visible:
        with reminders_module.autorelease_pool():
            t0 = time.monotonic()
            try:
                reconcile_project(
                    project, cfg, state, client, show_completed=show_completed
                )
                log.info("%s done in %.1fs", project.name, time.monotonic() - t0)
            except Exception as e:
                errs.append(f"{project.name}: {e}")
                log.exception("Reconcile failed for %s", project.name)
    if errs:
        raise RuntimeError("; ".join(errs[:5]))


def run() -> None:
    cfg = config_module.load()
    log.info(
        "Starting reminders-bridge: poll=%.3fs (fallback) statuses=%s prefix=%r",
        cfg.poll_interval_s,
        cfg.statuses,
        cfg.list_prefix,
    )
    state = state_module.load(cfg.state_path)
    try:
        sync_once(cfg, state)
    except Exception as e:
        log.exception("Initial sync error: %s", e)
    wrote = reminders_module.took_writes()
    try:
        watcher_module.install(reminders_module.get_store())
    except Exception as e:
        log.warning("Could not install change observer; polling only: %s", e)
    while True:
        # Floor the idle wait: EventKit edits are detected within ~settle_s by
        # the watcher regardless of this value, and every lane self-throttles to
        # >= several seconds, so polling faster than this only burns CPU re-running
        # the cheap per-cycle baseline with nothing to do. Honors a larger
        # user-set poll_ms; only clamps the wasteful sub-floor end.
        wait_s = max(_MIN_WAIT_S, float(cfg.poll_interval_s))
        woke = watcher_module.wait(wait_s, wrote)
        try:
            t0 = time.monotonic()
            sync_once(cfg, state, woke=woke)
            wrote = reminders_module.took_writes()
            log.info(
                "Sync (%s) in %.1fs",
                "event" if woke else "interval",
                time.monotonic() - t0,
            )
        except Exception as e:
            log.exception("Sync error: %s", e)
