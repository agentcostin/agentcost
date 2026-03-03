"""
Benchmark Runner — runs a model against professional tasks and measures economics.
This is the core engine: task assignment → LLM execution → quality evaluation → payment.
"""

from __future__ import annotations
import os
import time
import uuid
from datetime import datetime

from ..work.task_manager import TaskManager, Task
from ..work.evaluator import QualityEvaluator
from ..providers.tracked import TrackedProvider
from ..data.store import BenchmarkStore, TaskResult, RunSummary
from ..data.events import EventStore
from ..sdk.trace import TraceEvent


WORK_SYSTEM = """You are a professional completing a work task. Produce high-quality, 
detailed output that would be genuinely useful in a real professional context.
Be thorough, accurate, and well-organized. Your output will be evaluated for quality 
and you will be paid based on the score."""


class BenchmarkRunner:
    """
    Runs economic benchmarks: model executes tasks, gets quality-scored, gets paid.

    Usage::

        runner = BenchmarkRunner(model="gpt-4o", num_tasks=10)
        results = runner.run()
        runner.print_summary()
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        num_tasks: int = 10,
        sector: str | None = None,
        tasks_path: str | None = None,
        eval_model: str = "gpt-4o-mini",
        api_key: str | None = None,
        provider_name: str = "openai",
        base_url: str | None = None,
        eval_api_key: str | None = None,
        eval_provider: str | None = None,
        eval_base_url: str | None = None,
        verify_ssl: bool = True,
        store: BenchmarkStore | None = None,
    ):
        self.model = model
        self.num_tasks = num_tasks
        self.sector = sector
        self.run_id = f"run-{uuid.uuid4().hex[:8]}"

        self.task_manager = TaskManager(tasks_path)
        self.provider = TrackedProvider(
            model=model, api_key=api_key, provider=provider_name,
            base_url=base_url, verify_ssl=verify_ssl,
        )
        # For the evaluator: reuse provider config if set to proxy/ollama, otherwise default to openai
        _eval_provider = eval_provider or (provider_name if provider_name in ("proxy", "ollama") else "openai")
        _eval_key = eval_api_key or api_key
        _eval_url = eval_base_url or (base_url if provider_name in ("proxy", "ollama") else None)
        self.evaluator = QualityEvaluator(
            eval_model=eval_model,
            api_key=_eval_key,
            provider_name=_eval_provider,
            base_url=_eval_url,
            verify_ssl=verify_ssl,
        )
        self.store = store or BenchmarkStore()
        self.event_store = EventStore()

        self.results: list[TaskResult] = []
        self.started_at = ""
        self.finished_at = ""

    def run(self, verbose: bool = True) -> list[TaskResult]:
        """Execute the benchmark: run model against tasks, evaluate, calculate payment."""
        tasks = self.task_manager.get_tasks(count=self.num_tasks, sector=self.sector)
        if not tasks:
            print("No tasks available!")
            return []

        self.started_at = datetime.now().isoformat()
        total = len(tasks)

        if verbose:
            print(f"\n{'='*64}")
            print("  AgentCost Benchmark")
            print(f"  Model: {self.model}")
            print(f"  Provider: {self.provider.provider_name}"
                  + (f" → {self.provider.base_url}" if self.provider.base_url else ""))
            if not self.provider.verify_ssl:
                print("  SSL Verify: OFF (corporate gateway mode)")
            print(f"  Tasks: {total}" + (f" (sector: {self.sector})" if self.sector else ""))
            print(f"  Run ID: {self.run_id}")
            print(f"{'='*64}")

            # ── Preflight: test connectivity with a tiny call ────────
            print(f"\n  🔗 Testing connection to {self.model}...", end=" ", flush=True)
            try:
                test_result = self.provider.chat(
                    prompt="Reply with exactly: OK",
                    system="Reply with the single word OK and nothing else.",
                    temperature=None,  # Let the API use its default
                    max_tokens=10,
                )
                if test_result.content and len(test_result.content.strip()) > 0:
                    print(f"✅ Connected ({test_result.latency_ms:.0f}ms, "
                          f"${test_result.cost:.6f})")
                else:
                    # Got a response but content is empty — common with reasoning models
                    if test_result.output_tokens > 0:
                        print(f"✅ Connected ({test_result.latency_ms:.0f}ms, "
                              f"{test_result.output_tokens} output tokens)")
                        print("  ℹ️  Response had tokens but empty content — "
                              "normal for reasoning models (gpt-5, o1, o3)")
                    else:
                        print("⚠️  Got empty response — model may not be available")
                self.provider.reset_usage()  # Don't count the test call
            except Exception as e:
                err = str(e)
                print("❌ FAILED")
                print(f"\n  Error: {err[:300]}")
                if "401" in err or "auth" in err.lower():
                    print("  💡 Your API key or virtual key is invalid.")
                elif "404" in err or "not found" in err.lower():
                    print(f"  💡 Model '{self.model}' not found. Check the model name on your proxy.")
                elif "ssl" in err.lower() or "certificate" in err.lower() or "verify" in err.lower():
                    print("  💡 SSL certificate error. Your gateway likely uses an internal CA.")
                    print("     Fix: add --no-verify-ssl to your command.")
                elif "connect" in err.lower() or "refused" in err.lower():
                    print("  💡 Cannot reach the API. Check your --base-url or network.")
                    if self.provider.verify_ssl and self.provider.base_url and "https" in (self.provider.base_url or ""):
                        print("     If using a corporate gateway, try adding --no-verify-ssl")
                print("\n  Aborting benchmark. Fix the issue above and retry.\n")
                return []

            print()

        errors = 0
        for i, task in enumerate(tasks, 1):
            if verbose:
                print(f"  [{i}/{total}] {task.occupation} — {task.sector}")
                print(f"         Max payment: ${task.max_payment:.2f}")

            result = self._execute_task(task, verbose)
            self.results.append(result)
            self.store.save_task_result(result)

            if result.quality_score == 0 and result.input_tokens == 0:
                errors += 1

            if verbose:
                if result.input_tokens == 0 and result.quality_score == 0:
                    # Already printed error above in _execute_task
                    pass
                else:
                    emoji = "✅" if result.quality_score >= 0.7 else "⚠️" if result.quality_score >= 0.4 else "❌"
                    print(f"         {emoji} Quality: {result.quality_score:.2f} | "
                          f"Earned: ${result.actual_payment:.2f} | "
                          f"Cost: ${result.total_cost:.4f} | "
                          f"ROI: {result.roi:.0f}x")
                print()

        self.finished_at = datetime.now().isoformat()
        summary = self._build_summary()
        self.store.save_run_summary(summary)

        if verbose:
            if errors > 0:
                print(f"  ⚠️  {errors}/{total} tasks failed due to LLM errors.")
                if errors == total:
                    print("  💡 ALL tasks failed. Common causes:")
                    print("     • Wrong model name (check your proxy's model list)")
                    print("     • Invalid API key / virtual key")
                    print("     • Proxy not reachable or misconfigured")
                    print("     • Rate limit or quota exceeded")
                    print("\n  Try: python -m agentcost benchmark --model <model> --tasks 1 --provider proxy --base-url <url>")
                print()
            self._print_summary(summary)

        return self.results

    def _execute_task(self, task: Task, verbose: bool) -> TaskResult:
        """Execute a single task: LLM call → evaluate → calculate payment."""
        start = time.time()

        # Reset per-task usage tracking
        self.provider.reset_usage()

        # Execute the task
        prompt = (
            f"Complete the following professional task. Produce detailed, high-quality output.\n\n"
            f"Sector: {task.sector}\n"
            f"Role: {task.occupation}\n"
            f"Deliverable: {task.deliverable_type}\n\n"
            f"Task:\n{task.prompt}\n\n"
            f"Produce the complete deliverable now:"
        )

        error_msg = None
        try:
            llm_result = self.provider.chat(
                prompt=prompt,
                system=WORK_SYSTEM,
                temperature=0.7,
                max_tokens=4096,
            )
            work_output = llm_result.content
            llm_cost = self.provider.usage.total_cost
            input_tokens = self.provider.usage.total_input_tokens
            output_tokens = self.provider.usage.total_output_tokens

            # Log trace event so it appears in the dashboard
            self._log_trace(
                model=self.model, input_tokens=llm_result.input_tokens,
                output_tokens=llm_result.output_tokens, cost=llm_result.cost,
                latency_ms=llm_result.latency_ms, status="success",
                project=f"benchmark-{self.run_id}",
                agent_id=task.occupation,
            )

            if not work_output or len(work_output.strip()) < 10:
                error_msg = f"LLM returned empty/very short response ({len(work_output or '')} chars)"
                if verbose:
                    if output_tokens > 0 and input_tokens > 0:
                        # Model produced tokens but content is empty — reasoning model behavior
                        print(f"         ⚠️  {error_msg}")
                        print(f"            Tokens used: {input_tokens} in / {output_tokens} out")
                        print("            💡 This model may be a reasoning model (o1/o3/gpt-5) that")
                        print("               used all tokens for internal reasoning. The response")
                        print("               had output tokens but empty visible content.")
                    else:
                        print(f"         ⚠️  {error_msg}")

        except Exception as e:
            error_msg = str(e)
            work_output = ""
            llm_cost = 0.0
            input_tokens = 0
            output_tokens = 0

            # Log error trace
            self._log_trace(
                model=self.model, input_tokens=0, output_tokens=0, cost=0,
                latency_ms=0, status="error", error=error_msg[:500],
                project=f"benchmark-{self.run_id}",
                agent_id=task.occupation,
            )

            if verbose:
                # Show the actual error so users can diagnose
                err_str = str(e)
                # Truncate very long error messages but show enough to be useful
                if len(err_str) > 300:
                    err_str = err_str[:300] + "..."
                print(f"         🔴 LLM ERROR: {err_str}")

                # Common fixes
                if "401" in err_str or "auth" in err_str.lower() or "api key" in err_str.lower():
                    print("         💡 Check your API key / virtual key is valid")
                elif "404" in err_str or "not found" in err_str.lower():
                    print(f"         💡 Model '{self.model}' may not exist on your proxy. Check model name.")
                elif "connect" in err_str.lower() or "refused" in err_str.lower():
                    print("         💡 Cannot reach the API/proxy. Check --base-url or LITELLM_PROXY_URL")
                elif "timeout" in err_str.lower():
                    print("         💡 Request timed out. The model may be overloaded.")

        # Evaluate quality (skip if LLM failed)
        if error_msg and not work_output:
            quality_score = 0.0
            eval_cost = 0.0
            reasoning = f"Skipped — LLM error: {error_msg[:100]}"
        else:
            quality_score, eval_cost, reasoning = self.evaluator.evaluate(task, work_output)

        # Calculate payment
        actual_payment = quality_score * task.max_payment
        total_cost = llm_cost + eval_cost
        roi = actual_payment / total_cost if total_cost > 0 else 0
        duration = time.time() - start

        return TaskResult(
            run_id=self.run_id,
            task_id=task.task_id,
            model=self.model,
            sector=task.sector,
            occupation=task.occupation,
            quality_score=quality_score,
            max_payment=task.max_payment,
            actual_payment=actual_payment,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_cost=llm_cost,
            eval_cost=eval_cost,
            total_cost=total_cost,
            duration_seconds=duration,
            roi=roi,
            work_output=work_output[:2000],
            timestamp=datetime.now().isoformat(),
        )

    def _log_trace(self, model: str, input_tokens: int, output_tokens: int,
                   cost: float, latency_ms: float, status: str,
                   project: str, agent_id: str = None, error: str = None):
        """Log an LLM call as a trace event so it appears in the dashboard.

        Writes to:
          - Local database (SQLite or PostgreSQL via AGENTCOST_DATABASE_URL)
          - Remote API server (if AGENTCOST_SERVER_URL is set, e.g. http://localhost:8100)
        """
        event = TraceEvent(
            trace_id=f"{self.run_id}-{uuid.uuid4().hex[:8]}",
            project=project,
            model=model,
            provider=self.provider.provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            error=error,
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
        )

        # Write to local database
        try:
            self.event_store.log_trace(event)
        except Exception:
            pass

        # Also POST to remote API server if configured
        server_url = os.environ.get("AGENTCOST_SERVER_URL")
        if server_url:
            try:
                import urllib.request
                import json
                payload = json.dumps(event.to_dict()).encode()
                req = urllib.request.Request(
                    f"{server_url.rstrip('/')}/api/trace",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass  # Don't break benchmarks if remote logging fails

    def _build_summary(self) -> RunSummary:
        r = self.results
        # A task is "completed" only if the LLM actually produced output (tokens > 0)
        completed = [x for x in r if x.input_tokens > 0]
        failed = [x for x in r if x.input_tokens == 0]
        total_income = sum(x.actual_payment for x in r)
        total_cost = sum(x.total_cost for x in r)
        net = total_income - total_cost
        margin = (net / total_cost * 100) if total_cost > 0 else 0
        avg_q = sum(x.quality_score for x in completed) / len(completed) if completed else 0
        avg_roi = sum(x.roi for x in completed) / len(completed) if completed else 0

        return RunSummary(
            run_id=self.run_id,
            model=self.model,
            total_tasks=len(r),
            completed_tasks=len(completed),
            avg_quality=round(avg_q, 3),
            total_income=round(total_income, 2),
            total_cost=round(total_cost, 4),
            net_profit=round(net, 2),
            profit_margin=round(margin, 1),
            avg_roi=round(avg_roi, 1),
            total_input_tokens=sum(x.input_tokens for x in r),
            total_output_tokens=sum(x.output_tokens for x in r),
            total_duration=round(sum(x.duration_seconds for x in r), 1),
            started_at=self.started_at,
            finished_at=self.finished_at,
        )

    def _print_summary(self, s: RunSummary):
        print(f"\n{'='*64}")
        print(f"  BENCHMARK RESULTS — {self.model}")
        print(f"{'='*64}")
        print(f"  Run ID:          {s.run_id}")
        print(f"  Tasks:           {s.completed_tasks}/{s.total_tasks} completed"
              + (f" ({s.total_tasks - s.completed_tasks} failed)" if s.completed_tasks < s.total_tasks else ""))
        print(f"  Avg Quality:     {s.avg_quality:.3f}")
        print("")
        print("  💰 Economics:")
        print(f"     Total Income:    ${s.total_income:.2f}")
        print(f"     Total Cost:      ${s.total_cost:.4f}")
        print(f"     Net Profit:      ${s.net_profit:.2f}")
        print(f"     Profit Margin:   {s.profit_margin:.1f}%")
        print(f"     Avg ROI:         {s.avg_roi:.0f}x per task")
        print("")
        print("  📊 Token Usage:")
        print(f"     Input Tokens:    {s.total_input_tokens:,}")
        print(f"     Output Tokens:   {s.total_output_tokens:,}")
        print(f"     Total Duration:  {s.total_duration:.1f}s")
        print(f"{'='*64}\n")
