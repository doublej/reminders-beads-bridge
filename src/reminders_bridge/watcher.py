"""EKEventStoreChangedNotification observer: wake on iCloud sync, no polling."""

import logging
import threading
import time

from Foundation import (  # type: ignore[import-not-found, import-untyped]
    NSDate,
    NSNotificationCenter,
    NSObject,
    NSRunLoop,
)

try:
    from EventKit import EKEventStoreChangedNotification  # type: ignore[import-not-found, import-untyped]
except ImportError:
    EKEventStoreChangedNotification = "EKEventStoreChangedNotification"

log = logging.getLogger(__name__)
_RUN_MODE = "NSDefaultRunLoopMode"
_change = threading.Event()
_observer = None


class _StoreObserver(NSObject):
    def storeChanged_(self, note):
        _change.set()


def install(store) -> bool:
    global _observer
    if _observer is not None:
        return True
    _observer = _StoreObserver.alloc().init()
    NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        _observer, "storeChanged:",
        EKEventStoreChangedNotification, store,
    )
    log.info("Installed EKEventStoreChanged observer (event-driven sync)")
    return True


def _pump(seconds: float) -> None:
    end = time.monotonic() + seconds
    loop = NSRunLoop.currentRunLoop()
    while time.monotonic() < end:
        loop.runMode_beforeDate_(
            _RUN_MODE, NSDate.dateWithTimeIntervalSinceNow_(0.05)
        )


def wait(
    max_s: float, wrote: bool = True, settle_s: float = 0.6, debounce_s: float = 0.4
) -> bool:
    """Pump the runloop up to max_s; return True if a store change was observed.

    `settle_s` absorbs notifications fired by our own just-committed writes.
    `debounce_s` coalesces notification bursts from a single sync batch.

    `wrote` reports whether the preceding sync committed anything. When it
    didn't, there are no own-notifications to absorb, so we skip the settle
    pre-pump (pure idle overhead) and do not clear `_change` — preserving any
    external edit that landed during the sync so it wakes us immediately.

    When it did write, a change flagged *during* the settle pump is ambiguous:
    EKEventStoreChangedNotification is store-wide and identity-less, so our own
    write's notification and a concurrent external edit (e.g. a checkbox toggle)
    coalesce into the same signal. Clearing unconditionally silently dropped the
    external edit, deferring it to the lane's idle interval (up to ~30s). Instead
    we treat a settle-window change as possibly-external and force one
    confirmatory sync. This cannot busy-loop: syncs are idempotent, so if nothing
    external actually changed the follow-up writes nothing (`wrote=False`) and the
    next wait settles cleanly — the cost is one extra sync per self-write cycle,
    and self-writes only happen when there was real work to do.
    """
    if wrote:
        _pump(settle_s)
        settled_change = _change.is_set()
        _change.clear()
        if settled_change:
            return True
        deadline = time.monotonic() + max(0.0, max_s - settle_s)
    else:
        deadline = time.monotonic() + max_s
    loop = NSRunLoop.currentRunLoop()
    while time.monotonic() < deadline:
        loop.runMode_beforeDate_(
            _RUN_MODE, NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )
        if _change.is_set():
            _pump(debounce_s)
            _change.clear()
            return True
    return False
