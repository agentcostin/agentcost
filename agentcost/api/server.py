"""
AgentCost Dashboard API — FastAPI server with conditional enterprise features.

Editions:
  - Community (default): Core tracing, analytics, forecasting, optimizer, estimator
  - Enterprise: Adds SSO, orgs, budgets, policies, approvals, notifications, anomaly, gateway

Set AGENTCOST_EDITION=enterprise to force enterprise features.
Set AGENTCOST_EDITION=community to force community mode.
Default ('auto'): enterprise if modules are present.

Run: python -m agentcost.api.server
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from ..data.events import EventStore
from ..data.store import BenchmarkStore
from ..edition import get_edition, edition_info, ENTERPRISE

logger = logging.getLogger("agentcost.api")

# ── Resolve edition once at import time ──────────────────────────────────────
_edition = get_edition()
_ENTERPRISE = _edition == ENTERPRISE

# ── Auth imports: enterprise or community stubs ──────────────────────────────
if _ENTERPRISE:
    from ..auth.config import get_auth_config
    from ..auth.dependencies import get_optional_user, require_role
    from ..auth.models import AuthContext
    from ..auth.middleware import AuthMiddleware
else:
    from ..community_auth import (
        get_auth_config,
        get_optional_user,
        require_role,
        AuthContext,
        AuthMiddleware,
    )

# ── App creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgentCost API",
    version="1.0.0",
    description="AI Agent Cost Governance — track, control, and optimize LLM spending",
)

# ── Auto-migrate on startup ─────────────────────────────────────────────────


@app.on_event("startup")
async def _auto_migrate():
    """Apply schema migrations on startup (SQLite only; Postgres uses migration runner)."""
    from ..data.connection import get_db
    import pathlib

    db = get_db()
    if hasattr(db, "is_postgres") and db.is_postgres():
        return

    # Core migrations (always)
    core_mig = pathlib.Path(__file__).parent.parent / "data" / "migrations"
    _apply_sql_dir(
        db, core_mig, skip_files={"002_enterprise.sql"} if not _ENTERPRISE else set()
    )

    # Enterprise migrations (only if enterprise edition)
    if _ENTERPRISE:
        ent_mig = pathlib.Path(__file__).parent.parent / "data" / "migrations"
        _apply_sql_dir(db, ent_mig, only_files={"002_enterprise.sql"})


def _apply_sql_dir(db, mig_dir, skip_files=None, only_files=None):
    """Apply .sql files from a directory, adapting Postgres syntax for SQLite."""
    if not mig_dir.exists():
        return
    for sql_file in sorted(mig_dir.glob("*.sql")):
        if skip_files and sql_file.name in skip_files:
            continue
        if only_files and sql_file.name not in only_files:
            continue
        sql = sql_file.read_text()
        sql = sql.replace("TIMESTAMPTZ", "TEXT")
        sql = sql.replace("JSONB", "TEXT")
        sql = sql.replace("DOUBLE PRECISION", "REAL")
        sql = sql.replace("BOOLEAN", "INTEGER")
        sql = sql.replace("DEFAULT NOW()", "DEFAULT (datetime('now'))")
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        lines = [
            line
            for line in sql.split("\n")
            if "INSERT INTO schema_version" not in line and "ON CONFLICT" not in line
        ]
        sql = "\n".join(lines)
        try:
            db.executescript(sql)
        except Exception as e:
            logger.debug("Migration %s: %s", sql_file.name, e)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.add_middleware(AuthMiddleware)

# ── Enterprise routes (conditional) ──────────────────────────────────────────

if _ENTERPRISE:
    from ..auth.routes import auth_router
    from ..org.routes import org_router
    from ..cost.routes import cost_router
    from ..policy.routes import policy_router
    from ..notify.routes import notify_router

    app.include_router(auth_router)
    app.include_router(org_router)
    app.include_router(cost_router)
    app.include_router(policy_router)
    app.include_router(notify_router)


# ── Reaction Engine routes (open-source — available in all editions) ─────────

try:
    from ..reactions.routes import create_reaction_routes

    _reaction_router = create_reaction_routes()
    if _reaction_router:
        app.include_router(_reaction_router)
except ImportError:
    pass


# ── Model Registry API (open-source — serves vendored pricing to dashboard) ──

try:
    from ..cost.model_routes import router as model_router

    app.include_router(model_router)
except ImportError:
    pass


# ── Prompt Management (open-source — available in all editions) ──────────────

try:
    from ..prompts.routes import router as prompt_router

    app.include_router(prompt_router)
except ImportError:
    pass


# ── Feedback (open-source — available in all editions) ───────────────────────

try:
    from ..feedback.routes import router as feedback_router

    app.include_router(feedback_router)
except ImportError:
    pass


# ── OTel Collector (open-source — accept incoming OTLP spans) ────────────────

try:
    from ..otel.routes import router as otel_collector_router

    app.include_router(otel_collector_router)
except ImportError:
    pass


# ── Simulator (open-source — live cost chaos simulation) ─────────────────────

try:
    from ..simulator.routes import router as simulator_router

    app.include_router(simulator_router)
except ImportError:
    pass


@app.on_event("startup")
async def _start_reaction_engine():
    """Start the reaction engine and wire it to the EventBus."""
    try:
        from ..reactions import get_reaction_engine
        from ..plugins import registry

        engine = get_reaction_engine()
        engine.start()

        # Activate any loaded reactor plugins
        registry.activate_reactors(engine)

        logger.info("Reaction engine started with %d reactions", len(engine.reactions))
    except Exception as e:
        logger.warning("Reaction engine startup skipped: %s", e)


# ── Data layer singletons ────────────────────────────────────────────────────

_events: EventStore | None = None
_benchmarks: BenchmarkStore | None = None


def get_events():
    global _events
    if not _events:
        _events = EventStore()
    return _events


def get_benchmarks():
    global _benchmarks
    if not _benchmarks:
        _benchmarks = BenchmarkStore()
    return _benchmarks


# ── Dashboard HTML ───────────────────────────────────────────────────────────

_dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "..", "dashboard")
_dashboard_js_dir = os.path.join(_dashboard_dir, "js")
if os.path.isdir(_dashboard_js_dir):
    app.mount(
        "/dashboard/js", StaticFiles(directory=_dashboard_js_dir), name="dashboard-js"
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "dashboard", "index.html"
    )
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>AgentCost Dashboard</h1><p>Dashboard HTML not found.</p>")


@app.get("/models.js")
async def models_js():
    path = os.path.join(_dashboard_dir, "js", "models.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    return HTMLResponse("// models.js not found", status_code=404)


@app.get("/api.js")
async def api_js():
    path = os.path.join(_dashboard_dir, "js", "api.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    return HTMLResponse("// api.js not found", status_code=404)


# ══════════════════════════════════════════════════════════════════════════════
# CORE API ENDPOINTS (available in all editions)
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/health")
async def health():
    config = get_auth_config()
    info = edition_info()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        **info,
        "auth_enabled": getattr(config, "enabled", False),
    }


@app.get("/api/summary")
async def summary(
    project: str | None = None, user: AuthContext = Depends(get_optional_user)
):
    return get_events().get_cost_summary(project)


@app.get("/api/projects")
async def projects(user: AuthContext = Depends(get_optional_user)):
    return get_events().get_projects()


# ── Cost Breakdown ───────────────────────────────────────────────────────────


@app.get("/api/cost/by-model")
async def cost_by_model(
    project: str | None = None, user: AuthContext = Depends(get_optional_user)
):
    return get_events().get_cost_by_model(project)


@app.get("/api/cost/by-project")
async def cost_by_project(user: AuthContext = Depends(get_optional_user)):
    return get_events().get_cost_by_project()


@app.get("/api/cost/over-time")
async def cost_over_time(
    project: str | None = None,
    interval: str = Query("hour", pattern="^(minute|hour|day)$"),
    since_hours: int = 24,
    user: AuthContext = Depends(get_optional_user),
):
    return get_events().get_cost_over_time(project, interval, since_hours)


# ── Traces ───────────────────────────────────────────────────────────────────


@app.post("/api/trace")
async def ingest_trace(
    request: Request, user: AuthContext = Depends(get_optional_user)
):
    from ..sdk.trace import TraceEvent

    data = await request.json()
    event = TraceEvent(
        trace_id=data.get("trace_id", ""),
        project=data.get("project", "default"),
        model=data.get("model", "unknown"),
        provider=data.get("provider", "unknown"),
        input_tokens=data.get("input_tokens", 0),
        output_tokens=data.get("output_tokens", 0),
        cost=data.get("cost", 0),
        latency_ms=data.get("latency_ms", 0),
        status=data.get("status", "success"),
        error=data.get("error"),
        agent_id=data.get("agent_id"),
        session_id=data.get("session_id"),
        timestamp=data.get("timestamp", ""),
        metadata=data.get("metadata", {}),
    )
    get_events().log_trace(event)
    return {"status": "ok", "trace_id": event.trace_id}


@app.post("/api/trace/batch")
async def ingest_trace_batch(
    request: Request, user: AuthContext = Depends(get_optional_user)
):
    from ..sdk.trace import TraceEvent

    body = await request.json()
    items = body if isinstance(body, list) else body.get("events", [])
    count = 0
    for data in items:
        event = TraceEvent(
            trace_id=data.get("trace_id", ""),
            project=data.get("project", "default"),
            model=data.get("model", "unknown"),
            provider=data.get("provider", "unknown"),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cost=data.get("cost", 0),
            latency_ms=data.get("latency_ms", 0),
            status=data.get("status", "success"),
            error=data.get("error"),
            agent_id=data.get("agent_id"),
            session_id=data.get("session_id"),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )
        get_events().log_trace(event)
        count += 1
    return {"status": "ok", "count": count}


@app.get("/api/traces")
async def traces(
    project: str | None = None,
    model: str | None = None,
    since: str | None = None,
    limit: int = 100,
    user: AuthContext = Depends(get_optional_user),
):
    return get_events().get_traces(project, model, since, limit)


@app.get("/api/traces/count")
async def trace_count(
    project: str | None = None, user: AuthContext = Depends(get_optional_user)
):
    return {"count": get_events().get_event_count(project)}


# ── Budgets (basic — available in all editions) ─────────────────────────────


@app.get("/api/budget/{project}")
async def get_budget(project: str, user: AuthContext = Depends(get_optional_user)):
    return get_events().check_budget(project)


@app.post("/api/budget/{project}")
async def set_budget(
    project: str,
    daily: float | None = None,
    monthly: float | None = None,
    total: float | None = None,
    user: AuthContext = Depends(get_optional_user),
):
    get_events().set_budget(project, daily, monthly, total)
    return {"status": "ok", "project": project}


# ── Benchmarks ───────────────────────────────────────────────────────────────


@app.get("/api/benchmarks/leaderboard")
async def leaderboard(user: AuthContext = Depends(get_optional_user)):
    return get_benchmarks().get_model_leaderboard()


@app.get("/api/benchmarks/runs")
async def benchmark_runs(
    limit: int = 50, user: AuthContext = Depends(get_optional_user)
):
    return get_benchmarks().get_all_summaries(limit)


@app.get("/api/benchmarks/run/{run_id}")
async def benchmark_run(run_id: str, user: AuthContext = Depends(get_optional_user)):
    return get_benchmarks().get_run_results(run_id)


# ── Cost Intelligence (Phase 6 — all editions) ──────────────────────────────


@app.get("/api/forecast/{project}")
async def cost_forecast(
    project: str,
    days: int = 30,
    method: str = "ensemble",
    user: AuthContext = Depends(get_optional_user),
):
    from ..forecast import CostForecaster

    traces = get_events().get_traces(project, limit=10000)
    forecaster = CostForecaster()
    forecaster.add_from_traces(traces)
    return forecaster.predict(days_ahead=days, method=method).to_dict()


@app.get("/api/forecast/{project}/budget-exhaustion")
async def budget_exhaustion(
    project: str, budget: float = 100.0, user: AuthContext = Depends(get_optional_user)
):
    from ..forecast import CostForecaster

    traces = get_events().get_traces(project, limit=10000)
    forecaster = CostForecaster()
    forecaster.add_from_traces(traces)
    result = forecaster.predict_budget_exhaustion(budget)
    return result or {"message": "Budget not projected to be exhausted"}


@app.post("/api/estimate")
async def estimate_cost(
    request: Request, user: AuthContext = Depends(get_optional_user)
):
    from ..estimator import CostEstimator

    body = await request.json()
    estimator = CostEstimator()
    model = body.get("model", "gpt-4o")
    if "messages" in body:
        est = estimator.estimate_messages(
            model,
            body["messages"],
            task_type=body.get("task_type", "default"),
            max_output_tokens=body.get("max_output_tokens"),
        )
    else:
        est = estimator.estimate(
            model,
            body.get("prompt", ""),
            task_type=body.get("task_type", "default"),
            max_output_tokens=body.get("max_output_tokens"),
        )
    return est.to_dict()


@app.get("/api/estimate/compare")
async def estimate_compare(
    prompt: str = "Hello",
    task_type: str = "default",
    user: AuthContext = Depends(get_optional_user),
):
    from ..estimator import CostEstimator

    estimator = CostEstimator()
    popular = [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "claude-3-5-haiku",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "llama3:8b",
    ]
    return estimator.compare_models(prompt, popular, task_type)


@app.get("/api/analytics/{project}/summary")
async def analytics_summary(
    project: str, user: AuthContext = Depends(get_optional_user)
):
    from ..analytics import UsageAnalytics

    analytics = UsageAnalytics()
    analytics.add_traces(get_events().get_traces(project, limit=10000))
    return analytics.summary()


@app.get("/api/analytics/{project}/top-spenders")
async def analytics_top_spenders(
    project: str,
    by: str = "model",
    limit: int = 10,
    user: AuthContext = Depends(get_optional_user),
):
    from ..analytics import UsageAnalytics

    analytics = UsageAnalytics()
    analytics.add_traces(get_events().get_traces(project, limit=10000))
    return analytics.top_spenders(by=by, limit=limit)


@app.get("/api/analytics/{project}/efficiency")
async def analytics_efficiency(
    project: str, user: AuthContext = Depends(get_optional_user)
):
    from ..analytics import UsageAnalytics

    analytics = UsageAnalytics()
    analytics.add_traces(get_events().get_traces(project, limit=10000))
    return analytics.token_efficiency()


@app.get("/api/analytics/{project}/chargeback")
async def analytics_chargeback(
    project: str,
    group_by: str = "project",
    user: AuthContext = Depends(get_optional_user),
):
    from ..analytics import UsageAnalytics

    analytics = UsageAnalytics()
    analytics.add_traces(get_events().get_traces(project, limit=10000))
    return analytics.chargeback_report(group_by=group_by)


@app.get("/api/optimizer/{project}")
async def optimizer_report(
    project: str, user: AuthContext = Depends(get_optional_user)
):
    from ..optimizer import CostOptimizer

    optimizer = CostOptimizer()
    optimizer.add_traces(get_events().get_traces(project, limit=10000))
    return optimizer.analyze().to_dict()


# ══════════════════════════════════════════════════════════════════════════════
# ENTERPRISE-ONLY ENDPOINTS (registered dynamically)
# ══════════════════════════════════════════════════════════════════════════════

if _ENTERPRISE:

    @app.get("/api/admin/users")
    async def list_users(user: AuthContext = Depends(require_role("admin"))):
        from ..data.connection import get_db

        db = get_db()
        rows = db.fetch_all(
            "SELECT id, email, name, role, last_login_at, created_at FROM users "
            "WHERE org_id = ? ORDER BY created_at DESC",
            (user.org_id,),
        )
        return [dict(r) for r in rows]

    @app.get("/api/admin/org")
    async def get_org(user: AuthContext = Depends(require_role("admin"))):
        from ..data.connection import get_db

        db = get_db()
        row = db.fetch_one("SELECT * FROM orgs WHERE id = ?", (user.org_id,))
        return dict(row) if row else {"error": "Org not found"}

    @app.post("/api/admin/api-keys")
    async def create_api_key(
        name: str = "Default",
        scopes: str = "*",
        user: AuthContext = Depends(require_role("admin")),
    ):
        from ..auth.api_key import generate_api_key
        from ..data.connection import get_db
        import uuid

        db = get_db()
        full_key, key_prefix, key_hash = generate_api_key()
        key_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO api_keys (id, org_id, key_prefix, key_hash, name, scopes, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key_id,
                user.org_id,
                key_prefix,
                key_hash,
                name,
                scopes,
                user.sub,
                datetime.utcnow().isoformat(),
            ),
        )
        from ..org.audit_service import AuditService

        AuditService(db).log_api_key_event(user.org_id, user.sub, key_id, "create")
        return {
            "id": key_id,
            "key": full_key,
            "prefix": key_prefix,
            "name": name,
            "scopes": scopes,
            "message": "Save this key — it will not be shown again.",
        }

    @app.get("/api/admin/api-keys")
    async def list_api_keys(user: AuthContext = Depends(require_role("admin"))):
        from ..data.connection import get_db

        db = get_db()
        rows = db.fetch_all(
            "SELECT id, key_prefix, name, scopes, last_used, created_at "
            "FROM api_keys WHERE org_id = ? ORDER BY created_at DESC",
            (user.org_id,),
        )
        return [dict(r) for r in rows]

    @app.delete("/api/admin/api-keys/{key_id}")
    async def revoke_api_key(
        key_id: str, user: AuthContext = Depends(require_role("admin"))
    ):
        from ..data.connection import get_db

        db = get_db()
        db.execute(
            "DELETE FROM api_keys WHERE id = ? AND org_id = ?", (key_id, user.org_id)
        )
        from ..org.audit_service import AuditService

        AuditService(db).log_api_key_event(user.org_id, user.sub, key_id, "revoke")
        return {"status": "revoked", "id": key_id}

    @app.get("/api/events/history")
    async def event_history(
        event_type: str = None,
        limit: int = 50,
        user: AuthContext = Depends(get_optional_user),
    ):
        from ..events import get_event_bus

        return get_event_bus().get_history(event_type, limit)

    @app.get("/api/events/subscriptions")
    async def event_subscriptions(user: AuthContext = Depends(get_optional_user)):
        from ..events import get_event_bus

        return get_event_bus().subscriptions

    @app.post("/api/events/subscribe")
    async def event_subscribe(
        request: Request, user: AuthContext = Depends(get_optional_user)
    ):
        from ..events import get_event_bus
        from fastapi import HTTPException

        body = await request.json()
        url = body.get("url")
        if not url:
            raise HTTPException(400, "url is required")
        sub_id = get_event_bus().subscribe_webhook(
            url, body.get("event_types", ["*"]), body.get("secret", "")
        )
        return {"subscription_id": sub_id}

    @app.get("/api/events/stats")
    async def event_stats(user: AuthContext = Depends(get_optional_user)):
        from ..events import get_event_bus

        return get_event_bus().stats

    @app.get("/api/anomaly/baselines")
    async def anomaly_baselines(
        project: str = "default",
        model: str = "unknown",
        user: AuthContext = Depends(get_optional_user),
    ):
        try:
            from ..anomaly import AnomalyDetector  # noqa: F401

            return {"project": project, "model": model, "baselines": {}}
        except ImportError:
            return {"error": "Anomaly detection not available"}


# ── Gateway Cache Stats (all editions) ────────────────────────────────────────


@app.get("/api/gateway/cache/stats")
async def gateway_cache_stats(user: AuthContext = Depends(get_optional_user)):
    """Fetch cache stats from the AI Gateway (if running).

    Returns cache hit/miss counts, cost saved, hit rate, and per-project/model breakdown.
    If the gateway is not running, returns a placeholder with zeros.
    """
    gateway_url = os.getenv("AGENTCOST_GATEWAY_URL", "http://localhost:8200")
    try:
        import urllib.request
        import json as _json

        req = urllib.request.Request(
            f"{gateway_url}/v1/gateway/cache/stats", method="GET"
        )
        resp = urllib.request.urlopen(req, timeout=3)
        return _json.loads(resp.read().decode())
    except Exception:
        # Gateway not running — return empty stats
        return {
            "enabled": False,
            "entries": 0,
            "total_hits": 0,
            "total_misses": 0,
            "hit_rate_pct": 0,
            "total_cost_saved": 0,
            "total_latency_saved_ms": 0,
            "by_project": {},
            "by_model": {},
        }


# ── Seed endpoint (all editions) ─────────────────────────────────────────────


@app.post("/api/seed")
async def seed_sample_data(
    request: Request, user: AuthContext = Depends(get_optional_user)
):
    """Generate and insert sample trace data for testing."""
    import uuid as _uuid
    import random as _rand
    from ..sdk.trace import TraceEvent

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    days = int(body.get("days", 7))
    project_filter = body.get("project")
    clear = body.get("clear", False)
    base_calls = body.get("calls_per_day", 120)

    store = get_events()
    if clear:
        store.db.execute("DELETE FROM trace_events")

    models = [
        ("claude-sonnet-4-6", "anthropic", 3.0, 15.0, 1200, 800, 30),
        ("claude-opus-4-6", "anthropic", 5.0, 25.0, 2000, 1500, 8),
        ("claude-haiku-4-5", "anthropic", 0.8, 4.0, 600, 400, 20),
        ("gpt-5.2", "openai", 1.25, 10.0, 1500, 1000, 15),
        ("gpt-5.2-pro", "openai", 21.0, 168.0, 3000, 2000, 2),
        ("gpt-4.1-mini", "openai", 0.4, 1.6, 800, 500, 18),
        ("gpt-4.1-nano", "openai", 0.1, 0.4, 500, 300, 10),
        ("gemini-3-pro", "google", 2.0, 12.0, 1100, 900, 12),
        ("gemini-2.5-flash", "google", 0.15, 0.6, 700, 500, 15),
        ("deepseek-chat", "deepseek", 0.07, 1.1, 900, 700, 8),
        ("deepseek-reasoner", "deepseek", 0.55, 2.19, 1800, 1200, 3),
    ]
    projects_map = {
        "default": ["chatbot", "assistant"],
        "customer-support": [
            "ticket-classifier",
            "response-drafter",
            "escalation-agent",
        ],
        "data-pipeline": ["extractor", "transformer", "summarizer"],
        "code-review": ["reviewer", "security-scan"],
        "research": ["analyst"],
    }
    proj_weights = [35, 25, 20, 15, 5]
    proj_names = list(projects_map.keys())
    hourly_w = [
        1,
        1,
        1,
        1,
        1,
        2,
        4,
        8,
        12,
        15,
        14,
        13,
        10,
        14,
        15,
        14,
        12,
        10,
        7,
        5,
        3,
        2,
        2,
        1,
    ]
    dow_mult = [1.0, 1.1, 1.15, 1.1, 0.95, 0.4, 0.25]

    now = datetime.now()
    start = now - timedelta(days=days)
    count = 0
    total_cost = 0.0

    for day_off in range(days):
        day = start + timedelta(days=day_off)
        dow = day.weekday()
        day_calls = max(
            10,
            int(base_calls * dow_mult[dow] * (1.03**day_off)) + _rand.randint(-15, 15),
        )
        for _ in range(day_calls):
            hour = _rand.choices(range(24), weights=hourly_w, k=1)[0]
            ts = day.replace(
                hour=hour, minute=_rand.randint(0, 59), second=_rand.randint(0, 59)
            )
            mid, prov, inp, outp, avg_i, avg_o, _ = _rand.choices(
                models, weights=[m[6] for m in models], k=1
            )[0]
            if project_filter:
                proj = project_filter
                agent = _rand.choice(projects_map.get(proj, ["agent"]))
            else:
                proj = _rand.choices(proj_names, weights=proj_weights, k=1)[0]
                agent = _rand.choice(projects_map[proj])

            def jit(b):
                return max(1, _rand.randint(int(b * 0.6), int(b * 1.4)))

            i_tok, o_tok = jit(avg_i), jit(avg_o)
            cost = (i_tok * inp + o_tok * outp) / 1_000_000
            base_lat = 200 + o_tok * 0.5
            if "opus" in mid or "pro" in mid:
                base_lat *= 1.8
            elif "haiku" in mid or "nano" in mid or "flash" in mid:
                base_lat *= 0.5
            lat = max(50, base_lat * _rand.uniform(0.6, 1.5))
            status = "error" if _rand.random() < 0.03 else "success"
            err = (
                _rand.choice(
                    [
                        "Rate limit exceeded",
                        "Context length exceeded",
                        "Connection timeout",
                        "Internal server error",
                    ]
                )
                if status == "error"
                else None
            )
            if status == "error":
                cost = 0
                o_tok = 0
            event = TraceEvent(
                trace_id=_uuid.uuid4().hex[:12],
                project=proj,
                model=mid,
                provider=prov,
                input_tokens=i_tok,
                output_tokens=o_tok,
                cost=round(cost, 8),
                latency_ms=round(lat, 1),
                status=status,
                error=err,
                agent_id=agent,
                session_id=f"sess-{ts.strftime('%Y%m%d')}-{_rand.randint(1, 50):03d}",
                timestamp=ts.isoformat(),
                metadata={},
            )
            store.log_trace(event)
            count += 1
            total_cost += cost

    # ── Seed feedback on ~30% of traces ──────────────────────────
    feedback_count = 0
    try:
        from ..feedback import get_feedback_service

        fb_svc = get_feedback_service()
        recent = store.get_traces(limit=min(count, 500))
        comments_pos = [
            "Accurate and helpful",
            "Great response",
            "Exactly what I needed",
            "Fast and correct",
            "Well structured answer",
            "",
            "",
            "",
        ]
        comments_neg = [
            "Hallucinated a date",
            "Too verbose",
            "Missed the point",
            "Incorrect information",
            "Off topic",
            "",
            "",
        ]
        tags_neg = [
            ["hallucination"],
            ["verbose"],
            ["off-topic"],
            ["inaccurate"],
            [],
            [],
        ]
        sources = ["user", "user", "user", "dashboard", "automated", "human-review"]
        for trace in recent:
            if _rand.random() < 0.30:
                # 75% positive, 15% negative, 10% neutral
                r = _rand.random()
                if r < 0.75:
                    score = 1
                    comment = _rand.choice(comments_pos)
                elif r < 0.90:
                    score = -1
                    comment = _rand.choice(comments_neg)
                else:
                    score = 0
                    comment = ""
                fb_svc.submit(
                    trace["trace_id"],
                    score=score,
                    comment=comment,
                    source=_rand.choice(sources),
                    tags=_rand.choice(tags_neg) if score == -1 else [],
                )
                feedback_count += 1
    except Exception as e:
        logger.debug("Feedback seeding skipped: %s", e)

    return {
        "status": "ok",
        "seeded": count,
        "feedback_seeded": feedback_count,
        "days": days,
        "total_cost": round(total_cost, 2),
        "cleared": clear,
        "project_filter": project_filter,
    }


# ── Server run ────────────────────────────────────────────────────────────────


def run_server(host="0.0.0.0", port=None):
    import uvicorn

    if port is None:
        port = int(os.environ.get("AGENTCOST_PORT", "8500"))
    config = get_auth_config()
    auth_enabled = getattr(config, "enabled", False)

    print("\n🧮 AgentCost Dashboard API v1.0.0")
    print(f"   Edition:   {'🏢 Enterprise' if _ENTERPRISE else '🌐 Community'}")
    print(f"   http://{host}:{port}")
    print(f"   Dashboard: http://localhost:{port}/")
    print(f"   API docs:  http://localhost:{port}/docs")

    if _ENTERPRISE:
        print(
            f"   Auth:      {'✅ Enabled (Keycloak)' if auth_enabled else '⚠️  Disabled'}"
        )
        if auth_enabled:
            kc_url = getattr(config, "keycloak_url", "")
            print(f"   Keycloak:  {kc_url}")
            print(f"   Login:     http://localhost:{port}/auth/login")
            print(f"   SAML:      http://localhost:{port}/auth/saml/metadata")
    else:
        print("   Auth:      ⚠️  None (community mode)")

    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
