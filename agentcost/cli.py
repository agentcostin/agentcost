"""
AgentCost CLI — benchmark LLMs on real professional tasks.

Usage:
    python -m agentcost benchmark --model gpt-4o --tasks 10
    python -m agentcost compare --models "gpt-4o,gpt-4o-mini" --tasks 5
    python -m agentcost leaderboard
"""

from __future__ import annotations
import argparse
import sys
import os


def cmd_benchmark(args):
    """Run a single-model benchmark."""
    from .agent.benchmark_runner import BenchmarkRunner

    # --ollama-url is a shortcut for --provider ollama --base-url <url>
    if args.ollama_url:
        args.provider = "ollama"
        args.base_url = args.ollama_url
    elif args.provider == "ollama" and not args.base_url:
        args.base_url = os.environ.get("OLLAMA_HOST", "http://10.166.73.108:11434")

    runner = BenchmarkRunner(
        model=args.model,
        num_tasks=args.tasks,
        sector=args.sector,
        tasks_path=args.tasks_file,
        eval_model=args.eval_model,
        provider_name=args.provider,
        api_key=args.api_key,
        base_url=args.base_url,
        verify_ssl=not args.no_verify_ssl,
    )
    runner.run(verbose=True)

    if args.output:
        from .reports.cli_report import generate_markdown_report

        summary = runner._build_summary()
        md = generate_markdown_report([summary])
        with open(args.output, "w") as f:
            f.write(md)
        print(f"📄 Report saved to: {args.output}")


def cmd_compare(args):
    """Run a multi-model comparison."""
    from .agent.comparison import ModelComparison

    # --ollama-url is a shortcut for --provider ollama --base-url <url>
    if args.ollama_url:
        args.provider = "ollama"
        args.base_url = args.ollama_url
    elif args.provider == "ollama" and not args.base_url:
        args.base_url = os.environ.get("OLLAMA_HOST", "http://10.166.73.108:11434")

    models = [m.strip() for m in args.models.split(",")]

    comp = ModelComparison(
        models=models,
        num_tasks=args.tasks,
        sector=args.sector,
        tasks_path=args.tasks_file,
        eval_model=args.eval_model,
        default_provider=args.provider,
        default_api_key=args.api_key,
        default_base_url=args.base_url,
        verify_ssl=not args.no_verify_ssl,
    )
    comp.run(verbose=True)

    output = args.output or "benchmark-report.md"
    comp.save_markdown_report(output)


def cmd_leaderboard(args):
    """Show the all-time leaderboard from stored benchmark data."""
    from .data.store import BenchmarkStore

    store = BenchmarkStore()
    leaderboard = store.get_model_leaderboard()

    if not leaderboard:
        print("\nNo benchmark data yet. Run a benchmark first:")
        print("  python -m agentcost benchmark --model gpt-4o --tasks 5\n")
        return

    print(f"\n{'=' * 72}")
    print("  📊  ALL-TIME MODEL LEADERBOARD")
    print(f"{'=' * 72}")
    print()
    print(f"  {'Model':<32}{'Runs':<6}{'Quality':<10}{'ROI':<10}{'Income':<12}{'Cost'}")
    print(f"  {'─' * 32}{'─' * 6}{'─' * 10}{'─' * 10}{'─' * 12}{'─' * 10}")

    for row in leaderboard:
        print(
            f"  {row['model']:<32}{row['total_runs']:<6}"
            f"{row['avg_quality']:<10.3f}{row['avg_roi']:<10.1f}x"
            f"${row['total_income']:<11.2f}${row['total_cost']:.4f}"
        )

    print(f"\n{'=' * 72}\n")


def cmd_tasks(args):
    """List available tasks in the dataset."""
    from .work.task_manager import TaskManager

    tm = TaskManager(args.tasks_file)
    sectors = tm.get_sectors()

    print(f"\n📋 Task Dataset: {len(tm.tasks)} tasks across {len(sectors)} sectors\n")
    print(f"  Total potential value: ${tm.total_value:,.2f}\n")

    for sector in sectors:
        tasks = [t for t in tm.tasks if t.sector == sector]
        total = sum(t.max_payment for t in tasks)
        print(f"  {sector}: {len(tasks)} tasks (${total:,.2f} total value)")

    print()


def cmd_dashboard(args):
    """Launch the dashboard API server."""
    from .api.server import run_server

    run_server(host=args.host, port=args.port)


def cmd_traces(args):
    """Show recent trace events from the SDK."""
    from .data.events import EventStore

    store = EventStore()

    if args.summary:
        s = store.get_cost_summary(args.project)
        if not s or s.get("total_calls", 0) == 0:
            print("\nNo trace data yet. Instrument your code with the SDK:")
            print("  from agentcost.sdk import trace")
            print("  client = trace(OpenAI(), project='my-app')\n")
            return
        print(f"\n{'=' * 60}")
        print(
            "  📊 Cost Summary"
            + (f" — {args.project}" if args.project else " — All Projects")
        )
        print(f"{'=' * 60}")
        print(f"  Total Cost:      ${s['total_cost']:.6f}")
        print(f"  Total Calls:     {s['total_calls']:,}")
        print(f"  Input Tokens:    {s['total_input_tokens']:,}")
        print(f"  Output Tokens:   {s['total_output_tokens']:,}")
        print(f"  Avg Latency:     {s['avg_latency']:.0f}ms")
        print(f"  Models Used:     {s['model_count']}")
        print(f"{'=' * 60}")

        models = store.get_cost_by_model(args.project)
        if models:
            print("\n  By Model:")
            for m in models:
                print(
                    f"    {m['model']:<32} {m['calls']} calls  ${m['total_cost']:.6f}"
                )
        print()
        return

    traces = store.get_traces(project=args.project, limit=args.limit)
    if not traces:
        print("\nNo traces found. Instrument your code:")
        print("  from agentcost.sdk import trace")
        print("  client = trace(OpenAI(), project='my-app')\n")
        return

    print(
        f"\n  {'Time':<10}{'Model':<28}{'Tokens':<18}{'Cost':<14}{'Latency':<10}{'Status'}"
    )
    print(f"  {'─' * 10}{'─' * 28}{'─' * 18}{'─' * 14}{'─' * 10}{'─' * 8}")
    for t in traces:
        ts = t.get("timestamp") or ""
        ts_short = ts[11:19] if len(ts) > 19 else ts[:8]
        tokens = f"{t.get('input_tokens', 0):,}→{t.get('output_tokens', 0):,}"
        status = "✅" if t.get("status") == "success" else "❌"
        print(
            f"  {ts_short:<10}{t.get('model', '?'):<28}{tokens:<18}"
            f"${t.get('cost', 0):<13.6f}{t.get('latency_ms', 0):<10.0f}{status}"
        )
    print()


def cmd_budget(args):
    """View or set project budgets."""
    from .data.events import EventStore

    store = EventStore()

    if args.set_limit:
        store.set_budget(args.project, total_limit=args.set_limit)
        print(f"\n✅ Budget set: {args.project} → ${args.set_limit:.2f} total limit\n")
        return

    b = store.check_budget(args.project)
    if not b.get("has_budget"):
        print(f"\nNo budget set for '{args.project}'.")
        print(f"  Set one: python -m agentcost budget {args.project} --set 100.00\n")
        return

    pct = b.get("pct_used", 0)
    bar_len = 30
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    color_emoji = "🟢" if pct < 60 else "🟡" if pct < 80 else "🔴"

    print(f"\n  {color_emoji} Budget: {args.project}")
    print(f"  [{bar}] {pct:.1f}%")
    print(f"  Spent: ${b['current_spend']:.6f} / ${b['total_limit']:.2f}")
    if b.get("alerts"):
        for a in b["alerts"]:
            print(f"  ⚠️  Alert: {a['type']} ({a['pct'] * 100:.0f}%)")
    print()


def cmd_plugin(args):
    """Manage AgentCost plugins."""
    sub = getattr(args, "plugin_cmd", None)

    if sub == "list":
        from .plugins import registry

        discovered = registry.discover()
        for meta in discovered:
            if not registry.get(meta.name):
                try:
                    from importlib.metadata import entry_points

                    eps = entry_points()
                    if hasattr(eps, "select"):
                        group = eps.select(group="agentcost.plugins")
                    elif isinstance(eps, dict):
                        group = eps.get("agentcost.plugins", [])
                    else:
                        group = [ep for ep in eps if ep.group == "agentcost.plugins"]
                    for ep in group:
                        if ep.name == meta.name:
                            cls = ep.load()
                            registry.load(cls())
                            break
                except Exception:
                    pass
        all_plugins = registry.list_plugins()
        if not all_plugins:
            print("\nNo plugins installed.")
            print("  Install: agentcost plugin install <n>")
            print("  Create:  agentcost plugin create <n> --type notifier\n")
            return
        print(f"\n{'NAME':<25} {'VERSION':<10} {'TYPE':<12} {'HEALTHY':<8} DESCRIPTION")
        print("─" * 80)
        for p in all_plugins:
            icon = "✅" if p["healthy"] else "❌"
            print(
                f"{p['name']:<25} {p['version']:<10} {p['type']:<12} {icon:<8} {p.get('description', '')[:30]}"
            )
        print()

    elif sub == "install":
        import subprocess

        pkg = (
            f"agentcost-{args.name}"
            if not args.name.startswith("agentcost-")
            else args.name
        )
        print(f"\n📦 Installing {pkg}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"✅ {pkg} installed successfully\n")
        else:
            print(f"❌ Install failed:\n{result.stderr}\n")

    elif sub == "create":
        from .plugins.scaffold import scaffold_plugin

        path = scaffold_plugin(args.name, args.plugin_type)
        print(f"\n✅ Plugin scaffolded at: {path}/")
        print(f"   cd {path} && pip install -e .\n")

    elif sub == "test":
        from .plugins import registry

        for meta in registry.discover():
            if not registry.get(meta.name):
                try:
                    from importlib.metadata import entry_points

                    eps = entry_points()
                    if hasattr(eps, "select"):
                        group = eps.select(group="agentcost.plugins")
                    elif isinstance(eps, dict):
                        group = eps.get("agentcost.plugins", [])
                    else:
                        group = [ep for ep in eps if ep.group == "agentcost.plugins"]
                    for ep in group:
                        if ep.name == meta.name:
                            registry.load(ep.load()())
                            break
                except Exception:
                    pass
        plugins = registry.list_plugins()
        if args.name:
            plugins = [p for p in plugins if p["name"] == args.name]
        if not plugins:
            print("\nNo matching plugins found.\n")
            return
        for p in plugins:
            plugin_obj = registry.get(p["name"])
            health = plugin_obj.health_check() if plugin_obj else None
            status = "✅" if p["healthy"] else "❌"
            msg = f" — {health.message}" if health and not p["healthy"] else ""
            print(f"  {status} {p['name']} v{p['version']}{msg}")
        print()

    else:
        print("\nUsage: agentcost plugin {list|install|create|test}")
        print("  list              List installed plugins")
        print("  install NAME      Install a plugin from PyPI")
        print("  create NAME       Scaffold a new plugin project")
        print("  test [NAME]       Run plugin health checks\n")


def cmd_gateway(args):
    """Start the AI gateway proxy (enterprise feature)."""
    from .edition import is_enterprise

    if not is_enterprise():
        print("⚠️  AI Gateway is an enterprise feature.")
        print("   Set AGENTCOST_EDITION=enterprise to enable.")
        sys.exit(1)
    from .gateway import run_gateway

    run_gateway(host=args.host, port=args.port)


def cmd_info(args):
    """Show edition, features, and version info."""
    from .edition import edition_info, get_edition

    info = edition_info()
    edition = get_edition()

    print("\n🧮 AgentCost v1.0.0")
    print(
        f"   Edition: {'🏢 Enterprise' if edition == 'enterprise' else '🌐 Community'}"
    )

    # License info
    lic = info.get("license", {})
    if lic.get("tier") in ("trial", "enterprise"):
        print(f"   License: {lic['tier'].title()} ({lic.get('licensed_to', '')})")
        if lic.get("days_remaining") is not None:
            print(f"   Expires: {lic.get('days_remaining')} days remaining")
        if lic.get("max_users"):
            print(f"   Users:   {lic['max_users']} max")
        else:
            print("   Users:   Unlimited")
    elif edition == "enterprise":
        print("   License: Valid")
    else:
        print("   License: None (community)")

    print("\n   Core Features (MIT):")
    for feat, avail in info["core"].items():
        print(f"     {'✅' if avail else '❌'} {feat}")
    print("\n   Enterprise Features (BSL 1.1):")
    for feat, avail in info["features"].items():
        print(f"     {'✅' if avail else '🔒'} {feat}")
    print()


def cmd_license(args):
    """Manage license keys."""
    action = args.license_action

    if action == "status":
        from .license import get_license

        lic = get_license()
        print("\n🔑 License Status")
        print(f"   Valid:    {'✅ Yes' if lic.valid else '❌ No'}")
        print(f"   Tier:     {lic.tier}")
        print(f"   User:     {lic.licensed_to}")
        if lic.max_users:
            print(f"   Max Users: {lic.max_users}")
        else:
            print("   Max Users: Unlimited")
        if lic.expires_at:
            print(
                f"   Expires:  {lic.expires_at.strftime('%Y-%m-%d')} ({lic.days_remaining} days)"
            )
        else:
            print("   Expires:  Never")
        if lic.features:
            print(f"   Features: {', '.join(lic.features)}")
        if lic.error:
            print(f"   Error:    {lic.error}")
        print()

    elif action == "trial":
        from .license import generate_trial_key

        days = getattr(args, "days", 30) or 30
        key = generate_trial_key(days=days)
        print(f"\n🔑 Trial License Key ({days} days):\n")
        print(f"   {key}")
        print("\n   To activate, choose one:")
        print(f"     export AGENTCOST_LICENSE_KEY='{key}'")
        print(f"     echo '{key}' > ~/.agentcost/license.key")
        print()

    elif action == "activate":
        key = getattr(args, "key", None)
        if not key:
            print("❌ Provide a license key: agentcost license activate <key>")
            return
        from pathlib import Path
        from .license import _parse_key

        lic = _parse_key(key)
        if not lic.valid:
            print(f"❌ Invalid key: {lic.error}")
            return
        # Save to file
        key_dir = Path.home() / ".agentcost"
        key_dir.mkdir(exist_ok=True)
        key_file = key_dir / "license.key"
        key_file.write_text(key)
        print("\n✅ License activated!")
        print(f"   Tier:     {lic.tier}")
        print(f"   User:     {lic.licensed_to}")
        print(
            f"   Expires:  {lic.expires_at.strftime('%Y-%m-%d') if lic.expires_at else 'Never'}"
        )
        print(f"   Saved to: {key_file}")
        print()

    elif action == "deactivate":
        from pathlib import Path

        key_file = Path.home() / ".agentcost" / "license.key"
        if key_file.exists():
            key_file.unlink()
            print("✅ License deactivated. Reverted to community edition.")
        else:
            print("ℹ️  No license file found. Already on community edition.")
        # Also hint about env var
        if os.environ.get("AGENTCOST_LICENSE_KEY"):
            print(
                "⚠️  AGENTCOST_LICENSE_KEY env var is still set. Unset it to fully deactivate."
            )

    else:
        print("Usage: agentcost license [status|trial|activate <key>|deactivate]")


def main():
    parser = argparse.ArgumentParser(
        prog="agentcost",
        description="AgentCost — AI Agent Economic Benchmarking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct providers
  agentcost benchmark --model gpt-4o --tasks 5
  agentcost compare --models "gpt-4o,gpt-4o-mini" --tasks 10
  agentcost compare --models "gpt-4o,claude-sonnet-4-5-20250929" --tasks 5

  # Local Ollama (free — runs on your hardware)
  agentcost benchmark --model llama3.2 --provider ollama
  agentcost benchmark --model mistral:7b --provider ollama --ollama-url http://gpu-server:11434
  agentcost compare --models "llama3.2,mistral,phi3" --provider ollama --tasks 5

  # LiteLLM Proxy (virtual keys)
  agentcost benchmark --model gpt-4o --provider proxy --base-url http://localhost:4000 --api-key sk-virtual-123
  agentcost compare --models "gpt-4o,claude-sonnet-4-5-20250929" --provider proxy --base-url http://localhost:4000

  # LiteLLM SDK (100+ providers)
  agentcost benchmark --model groq/llama-3.1-70b-versatile --provider litellm
  agentcost compare --models "openai/gpt-4o,groq/llama-3.1-70b-versatile" --provider litellm

  # View results
  agentcost leaderboard
  agentcost tasks

  # Phase 2 — SDK tracing & dashboard
  agentcost dashboard                          # Start web dashboard on :8500
  agentcost traces --summary                   # Cost summary across all projects
  agentcost traces --project my-app --limit 20 # Recent traces for a project
  agentcost budget my-app --set 50.00          # Set $50 budget limit
  agentcost budget my-app                      # Check budget status
        """,
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Run a single-model benchmark")
    p_bench.add_argument(
        "--model", "-m", default="gpt-4o", help="Model name (default: gpt-4o)"
    )
    p_bench.add_argument(
        "--tasks", "-t", type=int, default=5, help="Number of tasks (default: 5)"
    )
    p_bench.add_argument("--sector", "-s", default=None, help="Filter by sector")
    p_bench.add_argument("--tasks-file", default=None, help="Path to tasks JSONL file")
    p_bench.add_argument(
        "--eval-model", default="gpt-4o-mini", help="Model for quality evaluation"
    )
    p_bench.add_argument(
        "--provider",
        default="openai",
        help="LLM provider: openai, anthropic, ollama, litellm, or proxy",
    )
    p_bench.add_argument("--api-key", default=None, help="API key (overrides env var)")
    p_bench.add_argument(
        "--base-url",
        default=None,
        help="Base URL for proxy/litellm-proxy (e.g. http://localhost:4000)",
    )
    p_bench.add_argument(
        "--ollama-url",
        default=None,
        help="Ollama server URL (default: http://10.166.73.108:11434). Shortcut for --provider ollama --base-url URL",
    )
    p_bench.add_argument(
        "--no-verify-ssl",
        action="store_true",
        default=False,
        help="Disable SSL certificate verification (for corporate gateways with internal CAs)",
    )
    p_bench.add_argument(
        "--output", "-o", default=None, help="Save markdown report to file"
    )

    # compare
    p_comp = sub.add_parser("compare", help="Compare multiple models head-to-head")
    p_comp.add_argument(
        "--models", "-m", required=True, help="Comma-separated model names"
    )
    p_comp.add_argument(
        "--tasks", "-t", type=int, default=5, help="Tasks per model (default: 5)"
    )
    p_comp.add_argument("--sector", "-s", default=None, help="Filter by sector")
    p_comp.add_argument("--tasks-file", default=None, help="Path to tasks JSONL file")
    p_comp.add_argument(
        "--eval-model", default="gpt-4o-mini", help="Model for quality evaluation"
    )
    p_comp.add_argument(
        "--provider",
        default="openai",
        help="LLM provider: openai, anthropic, ollama, litellm, or proxy",
    )
    p_comp.add_argument("--api-key", default=None, help="API key (overrides env var)")
    p_comp.add_argument(
        "--base-url",
        default=None,
        help="Base URL for proxy/litellm-proxy (e.g. http://localhost:4000)",
    )
    p_comp.add_argument(
        "--ollama-url",
        default=None,
        help="Ollama server URL (default: http://10.166.73.108:11434). Shortcut for --provider ollama --base-url URL",
    )
    p_comp.add_argument(
        "--no-verify-ssl",
        action="store_true",
        default=False,
        help="Disable SSL certificate verification (for corporate gateways with internal CAs)",
    )
    p_comp.add_argument(
        "--output", "-o", default=None, help="Save markdown report to file"
    )

    # leaderboard
    sub.add_parser("leaderboard", help="Show all-time model leaderboard")

    # tasks
    p_tasks = sub.add_parser("tasks", help="List available tasks")
    p_tasks.add_argument("--tasks-file", default=None, help="Path to tasks JSONL file")

    # dashboard (Phase 2)
    p_dash = sub.add_parser("dashboard", help="Launch the cost dashboard web UI")
    p_dash.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    p_dash.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AGENTCOST_PORT", "8500")),
        help="Port (default: 8500 or AGENTCOST_PORT)",
    )

    # traces (Phase 2)
    p_traces = sub.add_parser("traces", help="View SDK trace events")
    p_traces.add_argument("--project", "-p", default=None, help="Filter by project")
    p_traces.add_argument(
        "--limit", "-n", type=int, default=50, help="Number of traces (default: 50)"
    )
    p_traces.add_argument(
        "--summary",
        action="store_true",
        help="Show cost summary instead of individual traces",
    )

    # budget (Phase 2)
    p_budget = sub.add_parser("budget", help="View or set project budgets")
    p_budget.add_argument("project", help="Project name")
    p_budget.add_argument(
        "--set",
        dest="set_limit",
        type=float,
        default=None,
        help="Set total budget limit in dollars",
    )

    # ── Plugin commands (Phase 4) ────────────────────────────────────────────
    p_plugin = sub.add_parser("plugin", help="Manage AgentCost plugins")
    plugin_sub = p_plugin.add_subparsers(dest="plugin_cmd")
    plugin_sub.add_parser("list", help="List installed plugins")
    p_plugin_install = plugin_sub.add_parser(
        "install", help="Install a plugin from PyPI"
    )
    p_plugin_install.add_argument("name", help="Plugin name (e.g. slack-alerts)")
    p_plugin_create = plugin_sub.add_parser(
        "create", help="Scaffold a new plugin project"
    )
    p_plugin_create.add_argument("name", help="Plugin name")
    p_plugin_create.add_argument(
        "--type",
        dest="plugin_type",
        default="notifier",
        choices=["notifier", "policy", "exporter", "provider"],
    )
    p_plugin_test = plugin_sub.add_parser("test", help="Run plugin health checks")
    p_plugin_test.add_argument("name", nargs="?", help="Plugin name (omit for all)")

    # gateway
    p_gateway = sub.add_parser("gateway", help="Start the AI gateway proxy")
    p_gateway.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    p_gateway.add_argument(
        "--port", "-p", type=int, default=8200, help="Port (default: 8200)"
    )

    # info (Phase 7)
    sub.add_parser("info", help="Show edition, features, and version info")

    # license (Phase 7)
    p_license = sub.add_parser("license", help="Manage license keys")
    p_license.add_argument(
        "license_action",
        nargs="?",
        default="status",
        choices=["status", "trial", "activate", "deactivate"],
        help="License action (default: status)",
    )
    p_license.add_argument(
        "key", nargs="?", default=None, help="License key (for activate)"
    )
    p_license.add_argument(
        "--days", type=int, default=30, help="Trial duration in days (default: 30)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Route to command handler
    handlers = {
        "benchmark": cmd_benchmark,
        "compare": cmd_compare,
        "leaderboard": cmd_leaderboard,
        "tasks": cmd_tasks,
        "dashboard": cmd_dashboard,
        "traces": cmd_traces,
        "budget": cmd_budget,
        "plugin": cmd_plugin,
        "gateway": cmd_gateway,
        "info": cmd_info,
        "license": cmd_license,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
