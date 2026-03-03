"""
AgentCost Usage Analytics — Phase 6 Block 4

Rich analytics engine for cost data: top spenders, trends, token efficiency,
department chargeback reports. Exportable as CSV and JSON.

Usage:
    from agentcost.analytics import UsageAnalytics

    analytics = UsageAnalytics()
    analytics.add_traces(traces)

    # Top spenders
    print(analytics.top_spenders(by="project", limit=5))

    # Token efficiency
    print(analytics.token_efficiency())

    # Cost trends
    print(analytics.cost_trends(period="daily"))

    # Export
    analytics.export_csv("/path/to/report.csv")
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import csv
import io
import json


class UsageAnalytics:
    """Analytics engine for AgentCost trace data."""

    def __init__(self):
        self._traces: List[dict] = []

    def add_traces(self, traces: List[dict]):
        self._traces.extend(traces)

    def add_trace(self, trace: dict):
        self._traces.append(trace)

    def clear(self):
        self._traces.clear()

    @property
    def trace_count(self) -> int:
        return len(self._traces)

    # ── Top Spenders ─────────────────────────────────────────────────────

    def top_spenders(self, by: str = "model", limit: int = 10) -> List[dict]:
        """
        Rank top spenders by dimension.
        by: 'model', 'project', 'provider', 'agent_id'
        """
        agg = defaultdict(lambda: {"cost": 0, "calls": 0, "tokens": 0})
        for t in self._traces:
            key = t.get(by, "unknown")
            agg[key]["cost"] += float(t.get("cost", 0))
            agg[key]["calls"] += 1
            agg[key]["tokens"] += int(t.get("input_tokens", 0)) + int(t.get("output_tokens", 0))

        ranked = sorted(agg.items(), key=lambda x: -x[1]["cost"])[:limit]
        return [
            {
                by: name,
                "cost": round(data["cost"], 4),
                "calls": data["calls"],
                "tokens": data["tokens"],
                "cost_per_call": round(data["cost"] / data["calls"], 6) if data["calls"] > 0 else 0,
            }
            for name, data in ranked
        ]

    # ── Token Efficiency ─────────────────────────────────────────────────

    def token_efficiency(self) -> List[dict]:
        """
        Calculate token efficiency metrics per model.
        Measures output-to-input ratio, cost per token, tokens per call.
        """
        by_model = defaultdict(lambda: {"input": 0, "output": 0, "cost": 0, "calls": 0})
        for t in self._traces:
            model = t.get("model", "unknown")
            by_model[model]["input"] += int(t.get("input_tokens", 0))
            by_model[model]["output"] += int(t.get("output_tokens", 0))
            by_model[model]["cost"] += float(t.get("cost", 0))
            by_model[model]["calls"] += 1

        result = []
        for model, m in by_model.items():
            total_tokens = m["input"] + m["output"]
            result.append({
                "model": model,
                "input_tokens": m["input"],
                "output_tokens": m["output"],
                "total_tokens": total_tokens,
                "output_input_ratio": round(m["output"] / m["input"], 2) if m["input"] > 0 else 0,
                "cost_per_1k_tokens": round(m["cost"] / total_tokens * 1000, 6) if total_tokens > 0 else 0,
                "tokens_per_call": round(total_tokens / m["calls"]) if m["calls"] > 0 else 0,
                "cost": round(m["cost"], 4),
                "calls": m["calls"],
            })

        return sorted(result, key=lambda r: -r["cost"])

    # ── Cost Trends ──────────────────────────────────────────────────────

    def cost_trends(self, period: str = "daily", model: str = None) -> List[dict]:
        """
        Cost over time aggregated by period.
        period: 'daily', 'weekly', 'hourly'
        """
        agg = defaultdict(lambda: {"cost": 0, "calls": 0, "tokens": 0})

        for t in self._traces:
            if model and t.get("model") != model:
                continue

            ts = t.get("timestamp", "")
            if period == "hourly":
                key = ts[:13]  # YYYY-MM-DDTHH
            elif period == "weekly":
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    # ISO week
                    key = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
                except (ValueError, IndexError):
                    key = ts[:10]
            else:  # daily
                key = ts[:10]  # YYYY-MM-DD

            agg[key]["cost"] += float(t.get("cost", 0))
            agg[key]["calls"] += 1
            agg[key]["tokens"] += int(t.get("input_tokens", 0)) + int(t.get("output_tokens", 0))

        return [
            {"period": k, "cost": round(v["cost"], 4), "calls": v["calls"], "tokens": v["tokens"]}
            for k, v in sorted(agg.items())
        ]

    # ── Latency Analysis ─────────────────────────────────────────────────

    def latency_analysis(self) -> List[dict]:
        """Latency percentiles per model."""
        by_model = defaultdict(list)
        for t in self._traces:
            lat = float(t.get("latency_ms", 0))
            if lat > 0:
                by_model[t.get("model", "unknown")].append(lat)

        result = []
        for model, lats in by_model.items():
            lats.sort()
            n = len(lats)
            result.append({
                "model": model,
                "calls": n,
                "p50_ms": round(lats[n // 2], 1) if n > 0 else 0,
                "p90_ms": round(lats[int(n * 0.9)], 1) if n > 0 else 0,
                "p99_ms": round(lats[int(n * 0.99)], 1) if n > 0 else 0,
                "avg_ms": round(sum(lats) / n, 1) if n > 0 else 0,
                "min_ms": round(lats[0], 1) if n > 0 else 0,
                "max_ms": round(lats[-1], 1) if n > 0 else 0,
            })

        return sorted(result, key=lambda r: -r["calls"])

    # ── Chargeback Report ────────────────────────────────────────────────

    def chargeback_report(self, group_by: str = "project") -> dict:
        """
        Generate a chargeback report grouped by dimension.
        Returns summary + line items suitable for finance export.
        """
        groups = defaultdict(lambda: {"cost": 0, "calls": 0, "tokens": 0, "models": set()})

        for t in self._traces:
            key = t.get(group_by, "unassigned")
            groups[key]["cost"] += float(t.get("cost", 0))
            groups[key]["calls"] += 1
            groups[key]["tokens"] += int(t.get("input_tokens", 0)) + int(t.get("output_tokens", 0))
            groups[key]["models"].add(t.get("model", "unknown"))

        total_cost = sum(g["cost"] for g in groups.values())
        line_items = []
        for name, g in sorted(groups.items(), key=lambda x: -x[1]["cost"]):
            line_items.append({
                group_by: name,
                "cost": round(g["cost"], 4),
                "calls": g["calls"],
                "tokens": g["tokens"],
                "models_used": sorted(g["models"]),
                "pct_of_total": round(g["cost"] / total_cost * 100, 1) if total_cost > 0 else 0,
            })

        return {
            "report_type": "chargeback",
            "group_by": group_by,
            "total_cost": round(total_cost, 4),
            "line_items": line_items,
            "generated_at": datetime.now().isoformat(),
        }

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Overall usage summary."""
        total_cost = sum(float(t.get("cost", 0)) for t in self._traces)
        total_input = sum(int(t.get("input_tokens", 0)) for t in self._traces)
        total_output = sum(int(t.get("output_tokens", 0)) for t in self._traces)
        models = set(t.get("model", "unknown") for t in self._traces)
        projects = set(t.get("project", "unknown") for t in self._traces)
        errors = sum(1 for t in self._traces if t.get("status") == "error")

        return {
            "total_cost": round(total_cost, 4),
            "total_calls": len(self._traces),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "unique_models": len(models),
            "unique_projects": len(projects),
            "error_count": errors,
            "error_rate": round(errors / len(self._traces), 3) if self._traces else 0,
            "avg_cost_per_call": round(total_cost / len(self._traces), 6) if self._traces else 0,
        }

    # ── Export ────────────────────────────────────────────────────────────

    def export_csv(self, filepath: str = None) -> str:
        """
        Export traces as CSV. Returns CSV string if no filepath.
        """
        fields = [
            "timestamp", "project", "model", "provider", "input_tokens",
            "output_tokens", "cost", "latency_ms", "status",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in self._traces:
            writer.writerow({f: t.get(f, "") for f in fields})

        csv_content = output.getvalue()
        if filepath:
            with open(filepath, "w") as f:
                f.write(csv_content)
        return csv_content

    def export_json(self, filepath: str = None) -> str:
        """Export full analytics as JSON."""
        report = {
            "summary": self.summary(),
            "top_models": self.top_spenders(by="model", limit=10),
            "top_projects": self.top_spenders(by="project", limit=10),
            "token_efficiency": self.token_efficiency(),
            "latency_analysis": self.latency_analysis(),
        }
        json_str = json.dumps(report, indent=2, default=str)
        if filepath:
            with open(filepath, "w") as f:
                f.write(json_str)
        return json_str