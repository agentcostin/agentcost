"""
Report generators — terminal comparison tables and markdown reports.
"""

from __future__ import annotations
from datetime import datetime
from ..data.store import RunSummary


def print_comparison_report(summaries: list[RunSummary]):
    """Print a formatted comparison table to the terminal."""
    if not summaries:
        print("No results to compare.")
        return

    # Sort by ROI
    ranked = sorted(summaries, key=lambda s: s.avg_roi, reverse=True)

    print(f"\n{'='*80}")
    print("  🏆  MODEL COMPARISON — RANKED BY ROI")
    print(f"{'='*80}")
    print()
    print(f"  {'Rank':<6}{'Model':<32}{'Quality':<10}{'Income':<12}{'Cost':<12}{'ROI':<10}{'Margin'}")
    print(f"  {'─'*6}{'─'*32}{'─'*10}{'─'*12}{'─'*12}{'─'*10}{'─'*10}")

    for i, s in enumerate(ranked, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f" {i}"
        roi_str = f"{s.avg_roi:.0f}x" if s.avg_roi > 0 else "—"
        margin_str = f"{s.profit_margin:.0f}%" if s.total_income > 0 else "—"
        print(f"  {medal:<6}{s.model:<32}{s.avg_quality:<10.3f}"
              f"${s.total_income:<11.2f}${s.total_cost:<11.4f}"
              f"{roi_str:<10}{margin_str}")

    print()

    # Check if all models failed
    all_failed = all(s.avg_quality == 0 and s.total_income == 0 for s in ranked)
    if all_failed:
        print("  ⚠️  ALL MODELS SCORED ZERO — likely a configuration issue, not a quality issue.")
        print("  💡 Common causes:")
        print("     • Wrong model names (check what your proxy exposes)")
        print("     • Invalid API key / virtual key")
        print("     • SSL certificate issue with corporate gateway (try --no-verify-ssl)")
        print("     • Proxy returned errors that were silently caught")
        print("     • Run with a single task first to debug:")
        print("       python -m agentcost benchmark --model <name> --tasks 1 --provider proxy --base-url <url>")
    else:
        # Winner callout
        winner = ranked[0]
        print(f"  ✨ Winner: {winner.model}")
        print(f"     Earned ${winner.total_income:.2f} at {winner.avg_quality:.3f} quality")
        print(f"     for only ${winner.total_cost:.4f} in LLM costs ({winner.avg_roi:.0f}x ROI)")

        if len(ranked) > 1:
            loser = ranked[-1]
            diff = winner.avg_roi - loser.avg_roi
            print(f"\n  📉 {ranked[-1].model} earned {diff:.0f}x less per dollar than the winner")

    print(f"\n{'='*80}\n")

    # Per-model detail
    for s in ranked:
        print(f"  📊 {s.model}")
        print(f"     Tasks: {s.completed_tasks}/{s.total_tasks} | "
              f"Tokens: {s.total_input_tokens + s.total_output_tokens:,} | "
              f"Duration: {s.total_duration:.1f}s")
        hourly = (s.total_income / (s.total_duration / 3600)) if s.total_duration > 0 else 0
        print(f"     Equivalent hourly rate: ${hourly:,.0f}/hr")
        print()


def generate_markdown_report(summaries: list[RunSummary]) -> str:
    """Generate a full markdown comparison report."""
    if not summaries:
        return "# AgentCost Benchmark Report\n\nNo results available."

    ranked = sorted(summaries, key=lambda s: s.avg_roi, reverse=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# AgentCost Benchmark Report",
        "",
        f"**Generated:** {now}  ",
        f"**Tasks per model:** {ranked[0].total_tasks}  ",
        "**Evaluation model:** gpt-4o-mini  ",
        "",
        "## Model Rankings (by ROI)",
        "",
        "| Rank | Model | Avg Quality | Total Income | Total Cost | Avg ROI | Profit Margin |",
        "|------|-------|-------------|-------------|-----------|---------|---------------|",
    ]

    for i, s in enumerate(ranked, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)
        lines.append(
            f"| {medal} | {s.model} | {s.avg_quality:.3f} | "
            f"${s.total_income:.2f} | ${s.total_cost:.4f} | "
            f"{s.avg_roi:.0f}x | {s.profit_margin:.0f}% |"
        )

    lines.extend([
        "",
        "## Key Findings",
        "",
        f"**Winner: {ranked[0].model}** achieved the highest ROI at "
        f"{ranked[0].avg_roi:.0f}x — earning ${ranked[0].total_income:.2f} "
        f"from only ${ranked[0].total_cost:.4f} in LLM costs.",
        "",
    ])

    if len(ranked) > 1:
        lines.append(
            f"The gap between the best ({ranked[0].model}) and worst "
            f"({ranked[-1].model}) performing model is "
            f"{ranked[0].avg_roi - ranked[-1].avg_roi:.0f}x in ROI."
        )
        lines.append("")

    # Detailed per-model sections
    lines.extend(["## Detailed Results", ""])

    for s in ranked:
        hourly = (s.total_income / (s.total_duration / 3600)) if s.total_duration > 0 else 0
        lines.extend([
            f"### {s.model}",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Tasks Completed | {s.completed_tasks}/{s.total_tasks} |",
            f"| Average Quality | {s.avg_quality:.3f} |",
            f"| Total Income | ${s.total_income:.2f} |",
            f"| Total LLM Cost | ${s.total_cost:.4f} |",
            f"| Net Profit | ${s.net_profit:.2f} |",
            f"| Profit Margin | {s.profit_margin:.0f}% |",
            f"| Average ROI | {s.avg_roi:.0f}x |",
            f"| Input Tokens | {s.total_input_tokens:,} |",
            f"| Output Tokens | {s.total_output_tokens:,} |",
            f"| Total Duration | {s.total_duration:.1f}s |",
            f"| Equivalent Hourly Rate | ${hourly:,.0f}/hr |",
            "",
        ])

    lines.extend([
        "---",
        "*Generated by [AgentCost](https://github.com/agentcostin/agentcost) — "
        "AI Agent Economic Benchmarking*",
    ])

    return "\n".join(lines)
