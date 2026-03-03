"""
Multi-Model Comparison — runs multiple models on the same tasks and compares economics.
"""

from __future__ import annotations

from .benchmark_runner import BenchmarkRunner
from ..data.store import BenchmarkStore, RunSummary
from ..reports.cli_report import print_comparison_report, generate_markdown_report


class ModelComparison:
    """
    Runs the same benchmark across multiple models and produces a comparison.

    Usage::

        comp = ModelComparison(
            models=["gpt-4o", "claude-sonnet-4-5-20250929", "gpt-4o-mini"],
            num_tasks=10,
        )
        comp.run()
    """

    def __init__(
        self,
        models: list[str],
        num_tasks: int = 10,
        sector: str | None = None,
        tasks_path: str | None = None,
        eval_model: str = "gpt-4o-mini",
        api_keys: dict[str, str] | None = None,
        providers: dict[str, str] | None = None,
        default_provider: str = "openai",
        default_api_key: str | None = None,
        default_base_url: str | None = None,
        verify_ssl: bool = True,
    ):
        self.models = models
        self.num_tasks = num_tasks
        self.sector = sector
        self.tasks_path = tasks_path
        self.eval_model = eval_model
        self.api_keys = api_keys or {}
        self.providers = providers or {}
        self.default_provider = default_provider
        self.default_api_key = default_api_key
        self.default_base_url = default_base_url
        self.verify_ssl = verify_ssl
        self.store = BenchmarkStore()
        self.summaries: list[RunSummary] = []

    def _detect_provider(self, model: str) -> str:
        """Auto-detect provider from model name, falling back to default."""
        if model in self.providers:
            return self.providers[model]
        # If using proxy, ollama, or litellm globally, use that for all models
        if self.default_provider in ("proxy", "litellm", "ollama"):
            return self.default_provider
        if "claude" in model.lower():
            return "anthropic"
        return "openai"

    def _get_api_key(self, model: str, provider: str) -> str | None:
        if model in self.api_keys:
            return self.api_keys[model]
        return self.default_api_key

    def run(self, verbose: bool = True) -> list[RunSummary]:
        """Run benchmark for each model sequentially."""
        if verbose:
            print(f"\n{'=' * 64}")
            print("  AgentCost — Multi-Model Comparison")
            print(f"  Models: {', '.join(self.models)}")
            print(f"  Tasks per model: {self.num_tasks}")
            if self.sector:
                print(f"  Sector filter: {self.sector}")
            if self.default_provider in ("proxy", "litellm", "ollama"):
                print(
                    f"  Provider: {self.default_provider}"
                    + (f" ({self.default_base_url})" if self.default_base_url else "")
                )
            print(f"{'=' * 64}\n")

        for i, model in enumerate(self.models, 1):
            if verbose:
                print(f"\n{'─' * 64}")
                print(f"  Running model {i}/{len(self.models)}: {model}")
                print(f"{'─' * 64}")

            provider_name = self._detect_provider(model)
            api_key = self._get_api_key(model, provider_name)

            runner = BenchmarkRunner(
                model=model,
                num_tasks=self.num_tasks,
                sector=self.sector,
                tasks_path=self.tasks_path,
                eval_model=self.eval_model,
                api_key=api_key,
                provider_name=provider_name,
                base_url=self.default_base_url,
                verify_ssl=self.verify_ssl,
                store=self.store,
            )

            runner.run(verbose=verbose)
            summary = runner._build_summary()
            self.summaries.append(summary)

        # Print comparison
        if verbose:
            print_comparison_report(self.summaries)

        return self.summaries

    def save_markdown_report(self, path: str = "benchmark-report.md") -> str:
        """Generate and save a markdown comparison report."""
        md = generate_markdown_report(self.summaries)
        with open(path, "w") as f:
            f.write(md)
        print(f"\n📄 Markdown report saved to: {path}")
        return path
