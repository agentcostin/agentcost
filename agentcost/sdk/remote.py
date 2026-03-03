"""
RemoteTracker — batches trace events and sends them to an AgentCost API server.

Usage:
    from agentcost.sdk.remote import RemoteTracker

    tracker = RemoteTracker(
        endpoint="https://agentcost.company.com",
        api_key="ac_xxx",
        project="my-app",
    )
    tracker.start()

    # ... use trace() as normal — events auto-forwarded ...

    tracker.flush()   # force send
    tracker.stop()    # clean shutdown
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading

from .trace import TraceEvent, get_tracker

logger = logging.getLogger("agentcost.remote")


class RemoteTracker:
    """Collects trace events and periodically POSTs them to the AgentCost API."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        project: str = "default",
        batch_size: int = 50,
        flush_interval: float = 10.0,
        timeout: float = 5.0,
    ):
        self.endpoint = (endpoint or os.getenv("AGENTCOST_SERVER_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AGENTCOST_API_KEY", "")
        self.project = project
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.timeout = timeout

        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = False
        self._total_sent = 0
        self._total_errors = 0

    def start(self) -> "RemoteTracker":
        """Start the background flush timer and register the on_trace callback."""
        if self._running:
            return self
        self._running = True

        # Hook into CostTracker
        tracker = get_tracker(self.project)
        tracker.on_trace(self._on_event)

        # Schedule periodic flush
        self._schedule_flush()

        # Auto-flush on process exit
        atexit.register(self.flush)

        logger.info(f"RemoteTracker started → {self.endpoint} (project={self.project})")
        return self

    def stop(self):
        """Flush remaining events and stop the background timer."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self.flush()
        logger.info(
            f"RemoteTracker stopped — sent={self._total_sent}, errors={self._total_errors}"
        )

    def flush(self):
        """Send all buffered events to the server immediately."""
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        if not self.endpoint:
            logger.warning(
                "No AGENTCOST_SERVER_URL configured — dropping %d events", len(batch)
            )
            return

        self._send_batch(batch)

    def _on_event(self, event: TraceEvent):
        """Callback for CostTracker.on_trace — buffers events."""
        overflow = None
        with self._lock:
            self._buffer.append(event.to_dict())
            if len(self._buffer) >= self.batch_size:
                overflow = self._buffer[:]
                self._buffer.clear()
        if overflow:
            self._send_batch(overflow)

    def _schedule_flush(self):
        """Schedule the next periodic flush."""
        if not self._running:
            return
        self._timer = threading.Timer(self.flush_interval, self._periodic_flush)
        self._timer.daemon = True
        self._timer.start()

    def _periodic_flush(self):
        """Timer callback — flush and reschedule."""
        self.flush()
        self._schedule_flush()

    def _send_batch(self, batch: list[dict]):
        """POST a batch of events to /api/trace/batch."""
        url = f"{self.endpoint}/api/trace/batch"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            # Use urllib to avoid external dependency
            import urllib.request
            import urllib.error

            data = json.dumps({"events": batch}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status < 300:
                    self._total_sent += len(batch)
                    logger.debug(f"Sent {len(batch)} events → {resp.status}")
                else:
                    self._total_errors += len(batch)
                    logger.warning(f"Batch POST returned {resp.status}")
        except urllib.error.HTTPError as e:
            self._total_errors += len(batch)
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            logger.warning(f"Failed to send batch: {e} — {body}")
        except urllib.error.URLError as e:
            self._total_errors += len(batch)
            logger.warning(f"Failed to send batch: {e}")
        except Exception as e:
            self._total_errors += len(batch)
            logger.warning(f"Unexpected error sending batch: {e}")

    @property
    def stats(self) -> dict:
        """Return tracker stats."""
        return {
            "endpoint": self.endpoint,
            "project": self.project,
            "buffered": len(self._buffer),
            "total_sent": self._total_sent,
            "total_errors": self._total_errors,
            "running": self._running,
        }
