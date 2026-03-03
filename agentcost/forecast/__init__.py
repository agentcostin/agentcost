"""
AgentCost Cost Forecasting Engine — Phase 6 Block 1

Predicts future AI spending using historical trace data.
Supports linear regression and exponential smoothing methods.

Usage:
    from agentcost.forecast import CostForecaster
    forecaster = CostForecaster()
    forecaster.add_daily_cost("2026-02-01", 12.50)
    forecaster.add_daily_cost("2026-02-02", 14.20)
    ...
    prediction = forecaster.predict(days_ahead=30)
    print(prediction)
    # {'method': 'linear', 'forecasts': [...], 'total_predicted': 425.0,
    #  'daily_average': 14.17, 'trend': 'increasing', 'confidence': 0.85}
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DailySpend:
    """Single day's cost data."""
    date: str
    cost: float
    calls: int = 0
    tokens: int = 0


@dataclass
class Forecast:
    """Forecast result."""
    method: str
    forecasts: List[Dict]  # [{date, predicted_cost}, ...]
    total_predicted: float
    daily_average: float
    trend: str  # increasing, decreasing, stable
    trend_pct: float  # % change per day
    confidence: float  # R² for linear, smoothing quality
    current_daily_avg: float
    data_points: int

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "forecasts": self.forecasts,
            "total_predicted": round(self.total_predicted, 4),
            "daily_average": round(self.daily_average, 4),
            "trend": self.trend,
            "trend_pct": round(self.trend_pct, 2),
            "confidence": round(self.confidence, 4),
            "current_daily_avg": round(self.current_daily_avg, 4),
            "data_points": self.data_points,
        }


class CostForecaster:
    """
    Time-series cost forecasting with multiple methods.

    Methods:
        - linear: Ordinary least squares regression
        - ema: Exponential moving average (good for recent-weighted trends)
        - ensemble: Weighted average of both methods
    """

    def __init__(self):
        self._daily: List[DailySpend] = []

    @property
    def data_points(self) -> int:
        return len(self._daily)

    def add_daily_cost(self, date: str, cost: float, calls: int = 0, tokens: int = 0):
        """Add a daily cost observation."""
        self._daily.append(DailySpend(date=date, cost=cost, calls=calls, tokens=tokens))
        # Keep sorted by date
        self._daily.sort(key=lambda d: d.date)

    def add_from_traces(self, traces: List[dict]):
        """
        Build daily costs from a list of trace dicts.
        Each trace should have 'timestamp' and 'cost' keys.
        """
        daily_agg: Dict[str, DailySpend] = {}
        for t in traces:
            ts = t.get("timestamp", "")[:10]  # YYYY-MM-DD
            cost = float(t.get("cost", 0))
            tokens = int(t.get("input_tokens", 0)) + int(t.get("output_tokens", 0))
            if ts not in daily_agg:
                daily_agg[ts] = DailySpend(date=ts, cost=0, calls=0, tokens=0)
            daily_agg[ts].cost += cost
            daily_agg[ts].calls += 1
            daily_agg[ts].tokens += tokens

        for spend in daily_agg.values():
            self.add_daily_cost(spend.date, spend.cost, spend.calls, spend.tokens)

    def predict(self, days_ahead: int = 30, method: str = "ensemble") -> Forecast:
        """
        Predict future costs.

        Args:
            days_ahead: Number of days to forecast
            method: 'linear', 'ema', or 'ensemble'

        Returns:
            Forecast object with predictions
        """
        if len(self._daily) < 2:
            return self._empty_forecast(days_ahead, method)

        if method == "linear":
            return self._linear_forecast(days_ahead)
        elif method == "ema":
            return self._ema_forecast(days_ahead)
        elif method == "ensemble":
            return self._ensemble_forecast(days_ahead)
        else:
            raise ValueError(f"Unknown method: {method}. Use 'linear', 'ema', or 'ensemble'")

    def predict_budget_exhaustion(self, budget_limit: float) -> Optional[dict]:
        """
        Predict when a budget will be exhausted based on current trends.

        Returns dict with 'exhaustion_date', 'days_remaining', 'daily_burn_rate'
        or None if budget won't be exhausted (decreasing trend).
        """
        if len(self._daily) < 2:
            return None

        total_spent = sum(d.cost for d in self._daily)
        remaining = budget_limit - total_spent
        if remaining <= 0:
            return {
                "exhaustion_date": self._daily[-1].date,
                "days_remaining": 0,
                "daily_burn_rate": self._current_avg(),
                "total_spent": round(total_spent, 4),
                "budget_limit": budget_limit,
            }

        daily_rate = self._current_avg()
        if daily_rate <= 0:
            return None

        days_left = remaining / daily_rate
        last_date = datetime.strptime(self._daily[-1].date, "%Y-%m-%d")
        exhaust_date = last_date + timedelta(days=int(days_left))

        return {
            "exhaustion_date": exhaust_date.strftime("%Y-%m-%d"),
            "days_remaining": int(days_left),
            "daily_burn_rate": round(daily_rate, 4),
            "total_spent": round(total_spent, 4),
            "budget_limit": budget_limit,
        }

    def reset(self):
        """Clear all data."""
        self._daily.clear()

    # ── Linear Regression ────────────────────────────────────────────────

    def _linear_forecast(self, days_ahead: int) -> Forecast:
        """Ordinary least squares linear regression."""
        n = len(self._daily)
        costs = [d.cost for d in self._daily]

        # x = 0, 1, 2, ..., n-1
        x_mean = (n - 1) / 2.0
        y_mean = sum(costs) / n

        # Slope and intercept
        ss_xy = sum((i - x_mean) * (costs[i] - y_mean) for i in range(n))
        ss_xx = sum((i - x_mean) ** 2 for i in range(n))

        if ss_xx == 0:
            slope = 0
            intercept = y_mean
        else:
            slope = ss_xy / ss_xx
            intercept = y_mean - slope * x_mean

        # R² (coefficient of determination)
        ss_res = sum((costs[i] - (intercept + slope * i)) ** 2 for i in range(n))
        ss_tot = sum((costs[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Generate forecasts
        last_date = datetime.strptime(self._daily[-1].date, "%Y-%m-%d")
        forecasts = []
        for d in range(1, days_ahead + 1):
            x = n - 1 + d
            predicted = max(0, intercept + slope * x)
            fc_date = (last_date + timedelta(days=d)).strftime("%Y-%m-%d")
            forecasts.append({"date": fc_date, "predicted_cost": round(predicted, 4)})

        total = sum(f["predicted_cost"] for f in forecasts)
        daily_avg = total / days_ahead if days_ahead > 0 else 0
        trend, trend_pct = self._classify_trend(slope, y_mean)

        return Forecast(
            method="linear",
            forecasts=forecasts,
            total_predicted=total,
            daily_average=daily_avg,
            trend=trend,
            trend_pct=trend_pct,
            confidence=max(0, r_squared),
            current_daily_avg=self._current_avg(),
            data_points=n,
        )

    # ── Exponential Moving Average ───────────────────────────────────────

    def _ema_forecast(self, days_ahead: int, alpha: float = 0.3) -> Forecast:
        """Exponential smoothing forecast (weights recent data more)."""
        costs = [d.cost for d in self._daily]
        n = len(costs)

        # Calculate EMA
        ema = costs[0]
        for i in range(1, n):
            ema = alpha * costs[i] + (1 - alpha) * ema

        # EMA trend (difference between last two EMAs)
        if n >= 3:
            prev_ema = costs[0]
            for i in range(1, n - 1):
                prev_ema = alpha * costs[i] + (1 - alpha) * prev_ema
            trend_rate = ema - prev_ema
        else:
            trend_rate = 0

        # Generate forecasts with trend dampening
        last_date = datetime.strptime(self._daily[-1].date, "%Y-%m-%d")
        forecasts = []
        current = ema
        dampen = 0.95  # Trend dampens over time
        for d in range(1, days_ahead + 1):
            predicted = max(0, current + trend_rate * (dampen ** d))
            fc_date = (last_date + timedelta(days=d)).strftime("%Y-%m-%d")
            forecasts.append({"date": fc_date, "predicted_cost": round(predicted, 4)})

        total = sum(f["predicted_cost"] for f in forecasts)
        daily_avg = total / days_ahead if days_ahead > 0 else 0

        # Confidence based on prediction stability
        y_mean = sum(costs) / n
        trend, trend_pct = self._classify_trend(trend_rate, y_mean)

        # EMA confidence: how well does EMA track recent data?
        ema_errors = []
        e = costs[0]
        for i in range(1, n):
            e = alpha * costs[i] + (1 - alpha) * e
            ema_errors.append((costs[i] - e) ** 2)
        mse = sum(ema_errors) / len(ema_errors) if ema_errors else 0
        variance = sum((c - y_mean) ** 2 for c in costs) / n if n > 0 else 1
        confidence = max(0, 1 - mse / variance) if variance > 0 else 0

        return Forecast(
            method="ema",
            forecasts=forecasts,
            total_predicted=total,
            daily_average=daily_avg,
            trend=trend,
            trend_pct=trend_pct,
            confidence=confidence,
            current_daily_avg=self._current_avg(),
            data_points=n,
        )

    # ── Ensemble ─────────────────────────────────────────────────────────

    def _ensemble_forecast(self, days_ahead: int) -> Forecast:
        """Weighted average of linear and EMA forecasts."""
        linear = self._linear_forecast(days_ahead)
        ema = self._ema_forecast(days_ahead)

        # Weight by confidence
        total_conf = linear.confidence + ema.confidence
        if total_conf == 0:
            w_lin, w_ema = 0.5, 0.5
        else:
            w_lin = linear.confidence / total_conf
            w_ema = ema.confidence / total_conf

        # Blend forecasts
        forecasts = []
        for i in range(days_ahead):
            blended = (
                w_lin * linear.forecasts[i]["predicted_cost"]
                + w_ema * ema.forecasts[i]["predicted_cost"]
            )
            forecasts.append({
                "date": linear.forecasts[i]["date"],
                "predicted_cost": round(max(0, blended), 4),
            })

        total = sum(f["predicted_cost"] for f in forecasts)
        daily_avg = total / days_ahead if days_ahead > 0 else 0
        confidence = w_lin * linear.confidence + w_ema * ema.confidence

        # Use the higher-confidence method's trend
        if linear.confidence >= ema.confidence:
            trend, trend_pct = linear.trend, linear.trend_pct
        else:
            trend, trend_pct = ema.trend, ema.trend_pct

        return Forecast(
            method="ensemble",
            forecasts=forecasts,
            total_predicted=total,
            daily_average=daily_avg,
            trend=trend,
            trend_pct=trend_pct,
            confidence=confidence,
            current_daily_avg=self._current_avg(),
            data_points=self.data_points,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _current_avg(self) -> float:
        if not self._daily:
            return 0
        recent = self._daily[-7:] if len(self._daily) >= 7 else self._daily
        return sum(d.cost for d in recent) / len(recent)

    def _classify_trend(self, slope: float, mean: float) -> Tuple[str, float]:
        if mean == 0:
            return ("stable", 0.0)
        pct = (slope / mean) * 100
        if pct > 2:
            return ("increasing", pct)
        elif pct < -2:
            return ("decreasing", pct)
        else:
            return ("stable", pct)

    def _empty_forecast(self, days_ahead: int, method: str) -> Forecast:
        return Forecast(
            method=method, forecasts=[], total_predicted=0,
            daily_average=0, trend="unknown", trend_pct=0,
            confidence=0, current_daily_avg=0, data_points=self.data_points,
        )