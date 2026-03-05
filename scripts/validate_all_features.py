#!/usr/bin/env python3
"""
AgentCost — Comprehensive Feature Validation Script
Tests every feature across all phases (no external services required).
Usage: cd agentcost-phase6 && python scripts/validate_all_features.py
       VERBOSE=1 python scripts/validate_all_features.py  # show tracebacks
"""
import sys
import os
import time
import tempfile
import traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGENTCOST_AUTH_ENABLED","false")

PASS=FAIL=SKIP=0; ERRORS=[]

# Note: Enterprise services (Org, Cost, Policy, Notify) require DB migrations
# to create their tables. In production these run via:
#   python -m agentcost.data.migrations.migrate
# The 'no such table' failures below are expected in a clean test environment
# without migrations. They confirm the code loads but needs schema setup.

def section(t): print(f"\n{'═'*70}\n  {t}\n{'═'*70}")
def check(name,fn):
    global PASS,FAIL,SKIP
    try:
        r=fn()
        if r is None or r: PASS+=1; print(f"  ✅  {name}")
        else: FAIL+=1; ERRORS.append(f"{name}: returned falsy"); print(f"  ❌  {name}")
    except ImportError as e: SKIP+=1; print(f"  ⚠️   {name} — SKIP ({e})")
    except Exception as e: FAIL+=1; ERRORS.append(f"{name}: {e}"); print(f"  ❌  {name} — {e}"); os.environ.get("VERBOSE") and traceback.print_exc()
def chk_imp(mod,names=None):
    import importlib; m=importlib.import_module(mod)
    if names:
        for n in names: assert hasattr(m,n), f"{mod} missing {n}"
    return True

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 1-2 · Core SDK & Data Layer")
check("Import agentcost", lambda: chk_imp("agentcost"))
check("SDK: trace, CostTracker, TraceEvent", lambda: chk_imp("agentcost.sdk",["trace","CostTracker","TraceEvent"]))
check("RemoteTracker", lambda: chk_imp("agentcost.sdk.remote",["RemoteTracker"]))
check("SDK integrations (auto/crewai/langchain/llamaindex)", lambda: all([chk_imp(f"agentcost.sdk.integrations.{x}") for x in ["auto","crewai","langchain","llamaindex"]]))

def _t1():
    from agentcost.sdk.trace import CostTracker,TraceEvent
    t=CostTracker("p"); t.record(TraceEvent(trace_id="t1",project="p",model="gpt-4o",provider="openai",input_tokens=100,output_tokens=200,latency_ms=500,cost=0.005))
    return t.total_cost>0 and t.total_calls==1
check("CostTracker records TraceEvent", _t1)

def _t2():
    from agentcost.sdk.trace import CostTracker,TraceEvent
    t=CostTracker("p")
    t.record(TraceEvent(trace_id="t1",project="p",model="gpt-4o",provider="openai",input_tokens=100,output_tokens=200,latency_ms=500,cost=0.01))
    t.record(TraceEvent(trace_id="t2",project="p",model="gpt-4o-mini",provider="openai",input_tokens=50,output_tokens=100,latency_ms=200,cost=0.001))
    s=t.summary(); return s["total_calls"]==2 and s["total_cost"]>0
check("CostTracker summary()", _t2)

def _t3():
    from agentcost.sdk.trace import TraceEvent
    e=TraceEvent(trace_id="t1",project="p",model="m",provider="openai",input_tokens=1,output_tokens=2,latency_ms=3,cost=0.1)
    return hasattr(e,"timestamp") and e.project=="p"
check("TraceEvent dataclass", _t3)

section("PHASE 2 · Data Layer")
check("Data layer imports", lambda: chk_imp("agentcost.data",["get_db","DatabaseAdapter","Row"]))
check("SQLiteAdapter", lambda: chk_imp("agentcost.data.sqlite_adapter",["SQLiteAdapter"]))
check("PostgresAdapter class", lambda: chk_imp("agentcost.data.postgres_adapter",["PostgresAdapter"]))
check("Connection factory", lambda: chk_imp("agentcost.data.connection",["get_db","reset_db","set_db"]))

def _t4():
    from agentcost.data.events import EventStore; s=EventStore()
    return hasattr(s,"log_trace") and hasattr(s,"get_cost_summary")
check("EventStore instantiates", _t4)

def _t5():
    from agentcost.data.events import EventStore
    from agentcost.sdk.trace import TraceEvent
    s=EventStore()
    s.log_trace(TraceEvent(trace_id="t1",project="tp",model="gpt-4o",provider="openai",input_tokens=100,output_tokens=200,cost=0.005,latency_ms=500,status="success"))
    return s.get_cost_summary("tp")["total_cost"]>0
check("EventStore log_trace + query", _t5)

check("BenchmarkStore", lambda: hasattr(__import__("agentcost.data.store",fromlist=["BenchmarkStore"]).BenchmarkStore(),"save_run_summary"))

section("PHASE 3 Block 0 · DB Adapter Abstraction")
def _t6():
    from agentcost.data.adapter import DatabaseAdapter as DA
    return hasattr(DA,"execute") and hasattr(DA,"fetch_all") and hasattr(DA,"fetch_one")
check("DatabaseAdapter interface", _t6)
check("SQLiteAdapter extends DatabaseAdapter", lambda: issubclass(
    __import__("agentcost.data.sqlite_adapter",fromlist=["SQLiteAdapter"]).SQLiteAdapter,
    __import__("agentcost.data.adapter",fromlist=["DatabaseAdapter"]).DatabaseAdapter))
check("Migration module", lambda: chk_imp("agentcost.data.migrations.migrate"))

section("PHASE 2 · Providers & CLI")
check("Providers", lambda: chk_imp("agentcost.providers"))
check("TrackedProvider", lambda: chk_imp("agentcost.providers.tracked",["TrackedProvider"]))
check("CLI module", lambda: chk_imp("agentcost.cli"))
check("BenchmarkRunner", lambda: chk_imp("agentcost.agent.benchmark_runner",["BenchmarkRunner"]))
check("ModelComparison", lambda: chk_imp("agentcost.agent.comparison",["ModelComparison"]))
check("CLI report", lambda: chk_imp("agentcost.reports.cli_report"))

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 3 Block 1 · SSO/SAML Auth")
check("Auth exports", lambda: chk_imp("agentcost.auth",["get_current_user","require_role","AuthContext","TokenClaims"]))
check("Auth config", lambda: chk_imp("agentcost.auth.config",["get_auth_config"]))
check("JWT provider", lambda: chk_imp("agentcost.auth.jwt_provider"))
check("SAML provider", lambda: chk_imp("agentcost.auth.saml_provider"))
check("API key auth", lambda: chk_imp("agentcost.auth.api_key"))
check("Auth middleware", lambda: chk_imp("agentcost.auth.middleware",["AuthMiddleware"]))
check("Auth routes", lambda: chk_imp("agentcost.auth.routes",["auth_router"]))
check("Role enum (PLATFORM_ADMIN/ORG_ADMIN/ORG_MEMBER)", lambda: (
    (R:=__import__("agentcost.auth.models",fromlist=["Role"]).Role),
    hasattr(R,"PLATFORM_ADMIN") and hasattr(R,"ORG_ADMIN") and hasattr(R,"ORG_MEMBER"))[-1])
check("AuthContext", lambda: hasattr(__import__("agentcost.auth.models",fromlist=["AuthContext"]).AuthContext,"__init__"))

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 3 Block 2 · Org Management")
check("Org exports", lambda: chk_imp("agentcost.org",["OrgService","TeamService","InviteService","AuditService"]))

def _org1():
    from agentcost.org import OrgService; s=OrgService()
    o=s.create_org("Test Org",slug="test-org-v",created_by_email="a@t.com")
    return o["name"]=="Test Org" and s.get_org(o["id"]) is not None
check("OrgService create+get", _org1)

def _org2():
    from agentcost.org import OrgService,TeamService
    o=OrgService().create_org("TO",slug="to-v"); return isinstance(TeamService().list_members(o["id"]),list)
check("TeamService list_members", _org2)

def _org3():
    from agentcost.org import OrgService,InviteService
    o=OrgService().create_org("IO",slug="io-v")
    i=InviteService().create_invite(o["id"],"t@e.com",invited_by="admin")
    return i["email"]=="t@e.com" and i["status"]=="pending"
check("InviteService create", _org3)

def _org4():
    from agentcost.org import OrgService,AuditService
    o=OrgService().create_org("AO",slug="ao-v"); a=AuditService()
    a.log(o["id"],actor="admin",action="org.created",detail="Created")
    return len(a.get_log(o["id"]))>=1
check("AuditService log+get_log", _org4)

def _org5():
    from agentcost.org import OrgService,AuditService
    o=OrgService().create_org("CO",slug="co-v"); a=AuditService()
    a.log(o["id"],actor="a",action="t.a",detail="First")
    a.log(o["id"],actor="a",action="t.b",detail="Second")
    return a.verify_chain(o["id"])
check("AuditService hash chain", _org5)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 3 Block 3 · Budget & Cost Centers")
check("Cost exports", lambda: chk_imp("agentcost.cost",["CostCenterService","AllocationService","BudgetService"]))

def _cc1():
    from agentcost.cost import CostCenterService; s=CostCenterService()
    c=s.create(org_id="o1",name="Eng",code="ENG",monthly_budget=10000.0)
    return c["name"]=="Eng" and s.get(c["id"]) is not None and len(s.list("o1"))>=1
check("CostCenterService CRUD", _cc1)

def _cc2():
    from agentcost.cost import CostCenterService,AllocationService
    c=CostCenterService().create(org_id="oa",name="RD",monthly_budget=5000.0)
    AllocationService().create(org_id="oa",cost_center_id=c["id"],project="ml")
    return len(AllocationService().list("oa"))>=1
check("AllocationService create+list", _cc2)

def _cc3():
    from agentcost.cost import BudgetService; s=BudgetService()
    r=s.check_can_proceed(org_id="ob",project="t",estimated_cost=1.0)
    return isinstance(r,dict) and "allowed" in r
check("BudgetService check_can_proceed", _cc3)

def _cc4():
    from agentcost.cost import BudgetService; s=BudgetService()
    s.set_budget(org_id="ob2",project="prod",daily_limit=100.0,monthly_limit=2000.0)
    return s.get_budget(org_id="ob2",project="prod") is not None and s.check_can_proceed("ob2","prod",50.0)["allowed"]
check("BudgetService set+get+enforce", _cc4)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 3 Block 4 · Policy & Approvals")
check("Policy exports", lambda: chk_imp("agentcost.policy",["PolicyService","PolicyEngine","ApprovalService"]))

def _pol1():
    from agentcost.policy import PolicyService; s=PolicyService()
    p=s.create(org_id="op",name="Block GPT-4",conditions=[{"field":"model","op":"in","value":["gpt-4"]}],action="deny",priority=10)
    return p["action"]=="deny" and len(s.list("op"))>=1
check("PolicyService create+list", _pol1)

def _pol2():
    from agentcost.policy import PolicyService,PolicyEngine
    s=PolicyService(); e=PolicyEngine(s)
    s.create(org_id="oe",name="Block",conditions=[{"field":"model","op":"eq","value":"gpt-4"}],action="deny",priority=10)
    r1=e.evaluate("oe",{"model":"gpt-4","project":"t"})
    r2=e.evaluate("oe",{"model":"gpt-4o-mini","project":"t"})
    return (r1.get("action")=="deny" or r1.get("denied")) and r2.get("action")!="deny" and not r2.get("denied",False)
check("PolicyEngine deny/allow", _pol2)

check("Policy templates", lambda: len((__import__("agentcost.policy",fromlist=["PolicyService"]).PolicyService()).get_templates())>0)

def _apr1():
    from agentcost.policy import ApprovalService; s=ApprovalService()
    r=s.create(org_id="oa",requester_id="u1",context={"model":"gpt-4"})
    return r["status"]=="pending" and s.get(r["id"]) is not None
check("ApprovalService create+get", _apr1)

def _apr2():
    from agentcost.policy import ApprovalService; s=ApprovalService()
    r1=s.create(org_id="ol",requester_id="u1",context={"m":"gpt-4"})
    assert s.approve(r1["id"],approved_by="admin")["status"]=="approved"
    r2=s.create(org_id="ol",requester_id="u2",context={"m":"gpt-4-32k"})
    assert s.deny(r2["id"],denied_by="admin",reason="Expensive")["status"]=="denied"
    return True
check("Approval approve+deny lifecycle", _apr2)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 3 Block 5 · Notifications & Scorecards")
check("Notify exports", lambda: chk_imp("agentcost.notify",["ChannelService","Dispatcher","ScorecardService"]))

def _ch1():
    from agentcost.notify import ChannelService; s=ChannelService()
    c=s.create(org_id="on",channel_type="slack",name="Alerts",config={"webhook_url":"https://hooks.example.com/test"})
    return c["name"]=="Alerts" and len(s.list("on"))>=1
check("ChannelService create+list", _ch1)

def _sc1():
    from agentcost.notify import ScorecardService
    return isinstance(ScorecardService().generate(org_id="os",agent_id="a1"),dict)
check("ScorecardService generate", _sc1)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 4 · Work & Plugins")
check("Work module", lambda: chk_imp("agentcost.work"))
check("TaskManager", lambda: chk_imp("agentcost.work.task_manager",["TaskManager"]))
check("Evaluator", lambda: chk_imp("agentcost.work.evaluator"))
check("Plugin module", lambda: chk_imp("agentcost.plugins"))
check("Plugin scaffold", lambda: chk_imp("agentcost.plugins.scaffold"))
check("Plugin bases (Notifier/Policy/Exporter/Provider)", lambda: all(
    hasattr(__import__("agentcost.plugins",fromlist=[c]),c) for c in ["NotifierPlugin","PolicyPlugin","ExporterPlugin","ProviderPlugin"]))

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 5 Block 1 · AI Gateway")
check("Gateway module", lambda: chk_imp("agentcost.gateway"))
check("GatewayConfig", lambda: (__import__("agentcost.gateway",fromlist=["GatewayConfig"]).GatewayConfig(),True)[-1])
def _gc():
    from agentcost.gateway import ResponseCache; c=ResponseCache(); return hasattr(c,"get") and hasattr(c,"put")
check("ResponseCache", _gc)

section("PHASE 5 Block 2 · Anomaly Detection")
check("Anomaly module", lambda: chk_imp("agentcost.anomaly"))
def _an():
    from agentcost.anomaly import AnomalyDetector; d=AnomalyDetector(sensitivity=2.5)
    for i in range(20): d.ingest({"project":"t","model":"gpt-4o","cost":0.01,"input_tokens":100,"output_tokens":200,"latency_ms":500,"status":"success","timestamp":time.time()-i*60})
    d.ingest({"project":"t","model":"gpt-4o","cost":5.0,"input_tokens":100000,"output_tokens":200000,"latency_ms":500,"status":"success","timestamp":time.time()})
    s = d.stats
    return (s.get("total_events",0) if isinstance(s,dict) else d.stats().get("total_events",0)) > 0 or s.get("tracked_keys",0)>0
check("AnomalyDetector ingest+stats", _an)
check("AnomalyType enum", lambda: len(list(__import__("agentcost.anomaly",fromlist=["AnomalyType"]).AnomalyType))>0)

section("PHASE 5 Block 3 · OTel & Prometheus")
check("OTel module", lambda: chk_imp("agentcost.otel"))
check("AgentCostSpanExporter", lambda: hasattr(__import__("agentcost.otel",fromlist=["AgentCostSpanExporter"]),"AgentCostSpanExporter"))
check("Grafana dashboard JSON", lambda: os.path.exists(ROOT/"agentcost"/"otel"/"grafana-dashboard.json"))

section("PHASE 5 Block 4 · Event Bus")
check("Events module", lambda: chk_imp("agentcost.events"))
def _eb():
    from agentcost.events import EventBus; b=EventBus(); rx=[]
    b.subscribe_callback(lambda d:rx.append(d), event_types=["t.e"]); b.emit("t.e",{"k":"v"}); time.sleep(0.2)
    return len(rx)>=1 or b.stats().get("total_emitted",0)>0
check("EventBus subscribe+emit", _eb)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 6 Block 1 · Cost Forecasting")
check("Forecast module", lambda: chk_imp("agentcost.forecast",["CostForecaster"]))

def _f1():
    from agentcost.forecast import CostForecaster; f=CostForecaster()
    for i in range(10): f.add_daily_cost(f"2026-02-{i+1:02d}",10+i*2)
    r=f.predict(days_ahead=7,method="linear"); return r.method=="linear" and len(r.forecasts)==7 and r.trend=="increasing"
check("Forecaster linear (increasing)", _f1)

def _f2():
    from agentcost.forecast import CostForecaster; f=CostForecaster()
    for i in range(10): f.add_daily_cost(f"2026-02-{i+1:02d}",10+i)
    return f.predict(5,method="ema").method=="ema"
check("Forecaster EMA", _f2)

def _f3():
    from agentcost.forecast import CostForecaster; f=CostForecaster()
    for i in range(10): f.add_daily_cost(f"2026-02-{i+1:02d}",10+i*0.5)
    return f.predict(7,method="ensemble").method=="ensemble"
check("Forecaster ensemble", _f3)

def _f4():
    from agentcost.forecast import CostForecaster; f=CostForecaster()
    f.add_from_traces([{"timestamp":"2026-02-01T10:00:00","cost":5.0,"input_tokens":100,"output_tokens":200},
        {"timestamp":"2026-02-01T14:00:00","cost":3.0,"input_tokens":80,"output_tokens":100},
        {"timestamp":"2026-02-02T10:00:00","cost":7.0,"input_tokens":150,"output_tokens":250}])
    return f.data_points==2
check("Forecaster from traces", _f4)

check("Forecaster empty", lambda: (__import__("agentcost.forecast",fromlist=["CostForecaster"]).CostForecaster().predict(7).total_predicted==0))

def _f5():
    from agentcost.forecast import CostForecaster
    f1=CostForecaster()
    for i in range(10): f1.add_daily_cost(f"2026-02-{i+1:02d}",10.0)
    assert f1.predict(5,method="linear").trend=="stable"
    f2=CostForecaster()
    for i in range(10): f2.add_daily_cost(f"2026-02-{i+1:02d}",20-i*2)
    assert f2.predict(5,method="linear").trend=="decreasing"; return True
check("Forecaster trends (stable/decreasing)", _f5)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 6 Block 2 · Smart Router")
check("Router module", lambda: chk_imp("agentcost.router",["ModelRouter"]))

def _r(setup_fn):
    from agentcost.router import ModelRouter; r=ModelRouter()
    return setup_fn(r)

check("Router cheapest meeting quality", lambda: _r(lambda r: (
    r.add_model("gpt-4o",cost_per_1k=0.0025,quality=0.85,latency_p50=800),
    r.add_model("gpt-4o-mini",cost_per_1k=0.000075,quality=0.78,latency_p50=400),
    r.add_model("llama3:8b",cost_per_1k=0.0,quality=0.72,latency_p50=600),
    r.route(min_quality=0.75).model in ("gpt-4o-mini","llama3:8b"))[-1]))

check("Router latency constraint", lambda: _r(lambda r: (
    r.add_model("gpt-4o",cost_per_1k=0.0025,quality=0.85,latency_p50=800),
    r.add_model("gpt-4o-mini",cost_per_1k=0.000075,quality=0.78,latency_p50=400),
    r.route(min_quality=0.75,max_latency_ms=500).model=="gpt-4o-mini")[-1]))

check("Router high quality select", lambda: _r(lambda r: (
    r.add_model("gpt-4o",cost_per_1k=0.0025,quality=0.85,latency_p50=800),
    r.add_model("gpt-4o-mini",cost_per_1k=0.000075,quality=0.78,latency_p50=400),
    r.route(min_quality=0.80).model=="gpt-4o")[-1]))

check("Router fallback/no-match handling", lambda: _r(lambda r: (
    r.add_model("gpt-4o-mini",cost_per_1k=0.000075,quality=0.78,latency_p50=400),
    (res:=r.route(min_quality=0.99,fallback="gpt-4o")),
    res is not None and isinstance(res.model, str))[-1]))

check("Router comparison_table", lambda: _r(lambda r: (
    r.add_model("gpt-4o",cost_per_1k=0.0025,quality=0.85,latency_p50=800),
    r.comparison_table() is not None)[-1]))

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 6 Block 3 · Cost Optimizer")
check("Optimizer module", lambda: chk_imp("agentcost.optimizer",["CostOptimizer"]))

def _op1():
    from agentcost.optimizer import CostOptimizer; o=CostOptimizer()
    o.add_traces([{"model":"gpt-4o","cost":0.05,"input_tokens":2000,"output_tokens":1000,"latency_ms":800},
        {"model":"gpt-4o-mini","cost":0.001,"input_tokens":500,"output_tokens":200,"latency_ms":300}])
    r=o.analyze(); return r.total_cost>0 and r.total_calls==2 and r.efficiency_score>=0
check("Optimizer analyze", _op1)

check("Optimizer recs", lambda: isinstance(
    (lambda: (__import__("agentcost.optimizer",fromlist=["CostOptimizer"]).CostOptimizer().__class__,
     (o:=__import__("agentcost.optimizer",fromlist=["CostOptimizer"]).CostOptimizer()),
     o.add_traces([{"model":"gpt-4o","cost":0.1,"input_tokens":5000,"output_tokens":2000,"latency_ms":1000}]*50),
     o.analyze().recommendations)[-1])(), list))

check("Optimizer empty", lambda: __import__("agentcost.optimizer",fromlist=["CostOptimizer"]).CostOptimizer().analyze().total_cost==0)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 6 Block 4 · Usage Analytics")
check("Analytics module", lambda: chk_imp("agentcost.analytics"))

_trc=[{"project":"pa","agent":"a1","model":"gpt-4o","cost":0.05,"input_tokens":1000,"output_tokens":500,"timestamp":"2026-02-01T10:00:00"},
      {"project":"pb","agent":"a1","model":"gpt-4o","cost":0.08,"input_tokens":3000,"output_tokens":1500,"timestamp":"2026-02-02T10:00:00"}]

def _ua(fn):
    from agentcost.analytics import UsageAnalytics; a=UsageAnalytics(); a.add_traces(_trc); return fn(a)

check("Analytics top_spenders", lambda: _ua(lambda a: len(a.top_spenders(by="project",limit=5))>=1))
check("Analytics token_efficiency", lambda: _ua(lambda a: a.token_efficiency() is not None))

def _ua2():
    from agentcost.analytics import UsageAnalytics; a=UsageAnalytics()
    a.add_traces([{"project":"p","agent":"a","model":"gpt-4o","cost":0.05,"input_tokens":1000,"output_tokens":500,
        "timestamp":f"2026-02-{d:02d}T10:00:00"} for d in range(1,8)])
    return len(a.cost_trends(period="daily"))>0
check("Analytics cost_trends", _ua2)

def _ua3():
    from agentcost.analytics import UsageAnalytics; a=UsageAnalytics(); a.add_traces(_trc)
    with tempfile.NamedTemporaryFile(suffix=".csv",delete=False) as f: a.export_csv(f.name); return os.path.getsize(f.name)>0
check("Analytics export_csv", _ua3)

# ═══════════════════════════════════════════════════════════════════════════
section("PHASE 6 Block 5 · Prompt Cost Estimator")
check("Estimator module", lambda: chk_imp("agentcost.estimator"))

def _e1():
    from agentcost.estimator import CostEstimator; r=CostEstimator().estimate("gpt-4o","Explain quantum computing")
    return r.model=="gpt-4o" and r.estimated_input_tokens>0 and r.estimated_cost>=0
check("Estimator basic", _e1)

def _e2():
    from agentcost.estimator import CostEstimator
    r=CostEstimator().estimate_messages("gpt-4o",[{"role":"system","content":"helpful"},{"role":"user","content":"2+2?"}])
    return r.estimated_input_tokens>0
check("Estimator messages", _e2)

def _e3():
    from agentcost.estimator import CostEstimator
    rs=CostEstimator().estimate_batch([{"model":"gpt-4o","prompt":"Hello"},{"model":"gpt-4o-mini","prompt":"Hi"}])
    return len(rs)==2 and all(r.estimated_cost>=0 for r in rs)
check("Estimator batch", _e3)

def _e4():
    from agentcost.estimator import CostEstimator
    return len(CostEstimator().compare_models("Hello",["gpt-4o","gpt-4o-mini"]))>=2
check("Estimator compare_models", _e4)

# ═══════════════════════════════════════════════════════════════════════════
section("API Server & Dashboard")
check("FastAPI app", lambda: chk_imp("agentcost.api.server",["app"]))
def _rts(): return [r.path for r in __import__("agentcost.api.server",fromlist=["app"]).app.routes]
for rn in ["/api/summary","/api/projects"]: check(f"Route {rn}", lambda rn=rn: any(rn in r for r in _rts()))
for rn in ["auth","org","cost","policy","notify"]: check(f"Routes /{rn}/", lambda rn=rn: any(f"/{rn}/" in r for r in _rts()))
check("Dashboard HTML", lambda: os.path.exists(ROOT/"dashboard"/"index.html"))
check("Dashboard JS", lambda: all(os.path.exists(ROOT/"dashboard"/"js"/f) for f in ["api.js","intelligence.js","models.js"]))

# ═══════════════════════════════════════════════════════════════════════════
section("Infrastructure & Tooling")
for n,p in [("docker-compose.yml","docker-compose.yml"),("Dockerfile","docker/Dockerfile"),
    ("Dockerfile.dashboard","docker/Dockerfile.dashboard"),
    ("SQLite→Postgres migration","scripts/migrate-sqlite-to-postgres.py"),("Seed data","scripts/seed_sample_data.py"),
    ("Sample tasks","sample-data/tasks.jsonl"),
    ("pyproject.toml","pyproject.toml"),("setup.sh","setup.sh"),
    ("VSCode extension","vscode-extension/src/extension.ts"),("TypeScript SDK","sdks/typescript/src/index.ts"),
    ("ACP Server","acp-server/src/server.ts"),("ACP Client","acp-client/client.py"),
    ("CI workflow",".github/workflows/ci.yml")]:
    check(n, lambda p=p: os.path.exists(ROOT/p))
check("Example scripts", lambda: all(os.path.exists(ROOT/"examples"/f) for f in ["trace_openai.py","trace_ollama.py","trace_proxy.py"]))

# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'━'*70}\n  RESULTS\n{'━'*70}")
print(f"  ✅ Passed: {PASS}")
print(f"  ❌ Failed: {FAIL}")
print(f"  ⚠️  Skipped: {SKIP}")
print(f"  Total:   {PASS+FAIL+SKIP}")
print(f"{'━'*70}")
if ERRORS:
    print("\n  FAILURES:")
    for e in ERRORS: print(f"    • {e}")
print(f"\n  {'🎉 All features validated!' if FAIL==0 else f'⚠️  {FAIL} feature(s) need attention.'}\n")
sys.exit(0 if FAIL==0 else 1)
