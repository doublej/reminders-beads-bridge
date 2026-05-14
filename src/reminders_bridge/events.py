"""SSE consumer for /api/events/stream, with polling fallback.

The stream frame shape (from API.md):
  {type:"ready",   cwd, timestamp}
  {type:"heartbeat", timestamp}
  {type:"event",   name, originalType, issueId, issue, timestamp}

Unknown frame types are passed through to the handler unchanged; the handler
is responsible for filtering by `name` or `type`.
"""

import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

EventHandler = Callable[[dict], None]

# Server heartbeat is 25s; read timeout comfortably above that detects dead sockets.
_READ_TIMEOUT_S = 60.0


def _stream_url(base_url: str, project: Path) -> str:
    q = urllib.parse.quote(str(project), safe="/")
    return f"{base_url.rstrip('/')}/api/events/stream?project={q}"


@dataclass
class SSEClient:
    base_url: str
    on_event: EventHandler
    reconnect_s: float = 2.0

    def run(self, project: Path, stop: threading.Event) -> None:
        url = _stream_url(self.base_url, project)
        while not stop.is_set():
            try:
                self._consume(url, stop)
            except TimeoutError:
                log.info("SSE read timeout — reconnecting")
            except urllib.error.URLError as e:
                log.warning("SSE connect failed: %s", e.reason)
            except Exception as e:
                log.warning("SSE stream error: %s", e)
            if stop.wait(self.reconnect_s):
                return

    def _consume(self, url: str, stop: threading.Event) -> None:
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT_S) as r:
            for raw in r:
                if stop.is_set():
                    return
                if not raw.startswith(b"data:"):
                    continue
                payload = raw[5:].strip()
                if not payload:
                    continue
                try:
                    frame = json.loads(payload)
                except json.JSONDecodeError:
                    log.debug("SSE non-JSON frame: %r", payload[:120])
                    continue
                try:
                    self.on_event(frame)
                except Exception as e:
                    log.warning("SSE handler raised: %s", e)


def spawn(base_url: str, project: Path, on_event: EventHandler) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    client = SSEClient(base_url=base_url, on_event=on_event)
    t = threading.Thread(
        target=client.run,
        args=(project, stop),
        name=f"sse:{project.name}",
        daemon=True,
    )
    t.start()
    return t, stop
