"""
AgentCost Anomaly Detection — Phase 5 Block 2

Detects anomalies in AI cost and usage patterns:
  - Cost spikes: spending > N× the rolling average for this hour/project
  - Error bursts: sudden increase in error rates indicating provider issues
  - Latency anomalies: response times significantly above baseline
  - Token explosions: output tokens 10×+ the norm (runaway generation)

Uses a simple statistical approach (z-score on rolling windows) that works
without ML dependencies. Can be upgraded to ML-based detection later.

Usage:
    from agentcost.anomaly import AnomalyDetector, AnomalyType
    detector = AnomalyDetector(sensitivity=2.5)
    detector.ingest(event)  # feed trace events
    alerts = detector.check()  # returns list of AnomalyAlert
"""
from __future__ import annotations
import math
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Callable
from collections import defaultdict

logger = logging.getLogger("agentcost.anomaly")


class AnomalyType(str, Enum):
    COST_SPIKE = "cost_spike"
    ERROR_BURST = "error_burst"
    LATENCY_ANOMALY = "latency_anomaly"
    TOKEN_EXPLOSION = "token_explosion"


class Severity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnomalyAlert:
    """An anomaly detected in the trace data."""
    type: AnomalyType
    severity: Severity
    project: str
    model: str
    message: str
    value: float           # the observed value
    baseline: float        # the expected baseline
    z_score: float         # how many std devs away
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "project": self.project,
            "model": self.model,
            "message": self.message,
            "value": round(self.value, 6),
            "baseline": round(self.baseline, 6),
            "z_score": round(self.z_score, 2),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── Rolling Statistics ────────────────────────────────────────────────────────

class RollingStats:
    """Maintains rolling mean and std dev for a metric."""

    def __init__(self, window_size: int = 100):
        self._window: list[float] = []
        self._max = window_size

    def add(self, value: float) -> None:
        self._window.append(value)
        if len(self._window) > self._max:
            self._window.pop(0)

    @property
    def count(self) -> int:
        return len(self._window)

    @property
    def mean(self) -> float:
        if not self._window:
            return 0.0
        return sum(self._window) / len(self._window)

    @property
    def std(self) -> float:
        if len(self._window) < 2:
            return 0.0
        m = self.mean
        variance = sum((x - m) ** 2 for x in self._window) / len(self._window)
        return math.sqrt(variance)

    def z_score(self, value: float) -> float:
        """How many standard deviations is value from the mean."""
        s = self.std
        if s == 0:
            return 0.0 if value == self.mean else float("inf")
        return (value - self.mean) / s

    @property
    def last(self) -> float:
        return self._window[-1] if self._window else 0.0


# ── Anomaly Detector ──────────────────────────────────────────────────────────

class AnomalyDetector:
    """
    Detects anomalies in LLM trace events using rolling statistics.

    sensitivity: z-score threshold for anomaly detection (default 2.5 = ~99th percentile)
    window_size: number of recent events to use for baseline calculation
    min_samples: minimum events before anomaly detection activates
    error_rate_window: number of recent events to check for error rate
    error_rate_threshold: fraction of errors that triggers an alert (0.3 = 30%)
    """

    def __init__(
        self,
        sensitivity: float = 2.5,
        window_size: int = 100,
        min_samples: int = 10,
        error_rate_window: int = 20,
        error_rate_threshold: float = 0.3,
        on_anomaly: Optional[Callable[[AnomalyAlert], None]] = None,
    ):
        self.sensitivity = sensitivity
        self.window_size = window_size
        self.min_samples = min_samples
        self.error_rate_window = error_rate_window
        self.error_rate_threshold = error_rate_threshold
        self.on_anomaly = on_anomaly

        # Per (project, model) rolling stats
        self._cost_stats: dict[str, RollingStats] = defaultdict(lambda: RollingStats(window_size))
        self._latency_stats: dict[str, RollingStats] = defaultdict(lambda: RollingStats(window_size))
        self._output_token_stats: dict[str, RollingStats] = defaultdict(lambda: RollingStats(window_size))

        # Error tracking per (project, model)
        self._recent_statuses: dict[str, list[str]] = defaultdict(list)

        # Alert history (dedup)
        self._recent_alerts: dict[str, float] = {}  # alert_key -> timestamp
        self._alert_cooldown = 300  # 5 min between same alert type

        # Total alerts generated
        self.total_alerts: int = 0

    def _key(self, project: str, model: str) -> str:
        return f"{project}:{model}"

    def ingest(self, event) -> list[AnomalyAlert]:
        """
        Ingest a trace event and check for anomalies.
        Returns any anomalies detected from this event.

        event: TraceEvent or dict with keys: project, model, cost, latency_ms,
               output_tokens, status, timestamp
        """
        if isinstance(event, dict):
            project = event.get("project", "default")
            model = event.get("model", "unknown")
            cost = event.get("cost", 0)
            latency_ms = event.get("latency_ms", 0)
            output_tokens = event.get("output_tokens", 0)
            status = event.get("status", "success")
            ts = event.get("timestamp", "")
        else:
            project = getattr(event, "project", "default")
            model = getattr(event, "model", "unknown")
            cost = getattr(event, "cost", 0)
            latency_ms = getattr(event, "latency_ms", 0)
            output_tokens = getattr(event, "output_tokens", 0)
            status = getattr(event, "status", "success")
            ts = getattr(event, "timestamp", "")

        key = self._key(project, model)
        alerts: list[AnomalyAlert] = []

        # Track error status
        self._recent_statuses[key].append(status)
        if len(self._recent_statuses[key]) > self.error_rate_window:
            self._recent_statuses[key].pop(0)

        # Add to rolling stats BEFORE checking (check against historical baseline)
        cost_stats = self._cost_stats[key]
        latency_stats = self._latency_stats[key]
        token_stats = self._output_token_stats[key]

        # ── Check: Cost Spike ─────────────────────────────────────────────
        if cost > 0 and cost_stats.count >= self.min_samples:
            z = cost_stats.z_score(cost)
            if z > self.sensitivity:
                severity = Severity.CRITICAL if z > self.sensitivity * 2 else Severity.WARNING
                alert = AnomalyAlert(
                    type=AnomalyType.COST_SPIKE,
                    severity=severity,
                    project=project, model=model,
                    message=f"Cost ${cost:.4f} is {z:.1f}σ above average ${cost_stats.mean:.4f}",
                    value=cost, baseline=cost_stats.mean, z_score=z,
                    timestamp=ts,
                    metadata={"multiplier": round(cost / max(cost_stats.mean, 1e-9), 1)},
                )
                alerts.append(alert)

        # ── Check: Latency Anomaly ────────────────────────────────────────
        if latency_ms > 0 and latency_stats.count >= self.min_samples:
            z = latency_stats.z_score(latency_ms)
            if z > self.sensitivity:
                severity = Severity.CRITICAL if z > self.sensitivity * 2 else Severity.WARNING
                alert = AnomalyAlert(
                    type=AnomalyType.LATENCY_ANOMALY,
                    severity=severity,
                    project=project, model=model,
                    message=f"Latency {latency_ms}ms is {z:.1f}σ above average {latency_stats.mean:.0f}ms",
                    value=latency_ms, baseline=latency_stats.mean, z_score=z,
                    timestamp=ts,
                )
                alerts.append(alert)

        # ── Check: Token Explosion ────────────────────────────────────────
        if output_tokens > 0 and token_stats.count >= self.min_samples:
            z = token_stats.z_score(output_tokens)
            if z > self.sensitivity:
                multiplier = output_tokens / max(token_stats.mean, 1)
                if multiplier >= 5:  # Only flag if 5x+ the norm
                    severity = Severity.CRITICAL if multiplier >= 10 else Severity.WARNING
                    alert = AnomalyAlert(
                        type=AnomalyType.TOKEN_EXPLOSION,
                        severity=severity,
                        project=project, model=model,
                        message=f"Output tokens {output_tokens} is {multiplier:.0f}× the average {token_stats.mean:.0f}",
                        value=output_tokens, baseline=token_stats.mean, z_score=z,
                        timestamp=ts,
                        metadata={"multiplier": round(multiplier, 1)},
                    )
                    alerts.append(alert)

        # ── Check: Error Burst ────────────────────────────────────────────
        recent = self._recent_statuses[key]
        if len(recent) >= self.min_samples:
            error_count = sum(1 for s in recent if s != "success")
            error_rate = error_count / len(recent)
            if error_rate >= self.error_rate_threshold:
                alert = AnomalyAlert(
                    type=AnomalyType.ERROR_BURST,
                    severity=Severity.CRITICAL if error_rate > 0.5 else Severity.WARNING,
                    project=project, model=model,
                    message=f"Error rate {error_rate:.0%} ({error_count}/{len(recent)} recent calls)",
                    value=error_rate, baseline=self.error_rate_threshold, z_score=0,
                    timestamp=ts,
                    metadata={"error_count": error_count, "window_size": len(recent)},
                )
                alerts.append(alert)

        # Update stats AFTER checking
        if cost > 0:
            cost_stats.add(cost)
        if latency_ms > 0:
            latency_stats.add(latency_ms)
        if output_tokens > 0:
            token_stats.add(output_tokens)

        # Dedup and fire callbacks
        deduped = self._dedup_alerts(alerts)
        for alert in deduped:
            self.total_alerts += 1
            logger.warning(f"ANOMALY [{alert.type.value}] {alert.message}")
            if self.on_anomaly:
                try:
                    self.on_anomaly(alert)
                except Exception as e:
                    logger.error(f"Anomaly callback error: {e}")

        return deduped

    def _dedup_alerts(self, alerts: list[AnomalyAlert]) -> list[AnomalyAlert]:
        """Filter out alerts that fired recently (within cooldown)."""
        now = time.time()
        result = []
        for alert in alerts:
            key = f"{alert.type.value}:{alert.project}:{alert.model}"
            last = self._recent_alerts.get(key, 0)
            if now - last > self._alert_cooldown:
                self._recent_alerts[key] = now
                result.append(alert)
        return result

    def get_baselines(self, project: str, model: str) -> dict:
        """Get current baseline statistics for a project/model."""
        key = self._key(project, model)
        return {
            "cost": {"mean": self._cost_stats[key].mean, "std": self._cost_stats[key].std,
                     "samples": self._cost_stats[key].count},
            "latency_ms": {"mean": self._latency_stats[key].mean, "std": self._latency_stats[key].std,
                           "samples": self._latency_stats[key].count},
            "output_tokens": {"mean": self._output_token_stats[key].mean,
                              "std": self._output_token_stats[key].std,
                              "samples": self._output_token_stats[key].count},
        }

    def reset(self, project: str = None, model: str = None) -> None:
        """Reset baselines. If project/model given, reset just that key."""
        if project and model:
            key = self._key(project, model)
            self._cost_stats.pop(key, None)
            self._latency_stats.pop(key, None)
            self._output_token_stats.pop(key, None)
            self._recent_statuses.pop(key, None)
        else:
            self._cost_stats.clear()
            self._latency_stats.clear()
            self._output_token_stats.clear()
            self._recent_statuses.clear()
            self._recent_alerts.clear()

    @property
    def stats(self) -> dict:
        return {
            "tracked_keys": len(self._cost_stats),
            "total_alerts": self.total_alerts,
            "sensitivity": self.sensitivity,
            "min_samples": self.min_samples,
        }


# ── Convenience: attach to CostTracker ────────────────────────────────────────

def attach_anomaly_detection(
    project: str = "default",
    sensitivity: float = 2.5,
    on_anomaly: Optional[Callable[[AnomalyAlert], None]] = None,
) -> AnomalyDetector:
    """
    Attach anomaly detection to a CostTracker.

    Usage:
        from agentcost.anomaly import attach_anomaly_detection
        detector = attach_anomaly_detection(project="my-project", sensitivity=2.5)
    """
    from ..sdk.trace import get_tracker
    tracker = get_tracker(project)
    detector = AnomalyDetector(sensitivity=sensitivity, on_anomaly=on_anomaly)
    tracker.on_trace(lambda event: detector.ingest(event))
    logger.info(f"Anomaly detection attached to project={project} (sensitivity={sensitivity}σ)")
    return detector
