"""
Quality Evaluator — uses an LLM to score task output quality on a 0–1 scale.
"""

from __future__ import annotations
from .task_manager import Task
from ..providers.tracked import TrackedProvider
import json
import re


EVAL_SYSTEM = """You are an expert evaluator assessing the quality of professional work output.
You will receive a task description and the work produced by an AI agent.
Score the quality on a scale of 0.0 to 1.0 based on:
- Completeness: Does it address all requirements in the task?
- Accuracy: Is the content factually correct and professionally sound?
- Clarity: Is it well-organized, clear, and professionally written?
- Usefulness: Would a professional find this output genuinely useful?

Respond with ONLY a JSON object: {"score": 0.XX, "reasoning": "brief explanation"}"""

EVAL_PROMPT = """## Task Description
Sector: {sector}
Occupation: {occupation}
Deliverable Type: {deliverable_type}

Task:
{prompt}

## Work Output
{output}

## Evaluation
Score this work output from 0.0 (completely inadequate) to 1.0 (exceptional professional quality).
Respond with ONLY a JSON object: {{"score": 0.XX, "reasoning": "brief explanation"}}"""


class QualityEvaluator:
    """
    Evaluates AI work output quality using an LLM judge.
    Tracks evaluation costs separately from agent work costs.
    """

    def __init__(
        self,
        eval_model: str = "gpt-4o-mini",
        api_key: str | None = None,
        provider_name: str = "openai",
        base_url: str | None = None,
        verify_ssl: bool = True,
    ):
        self.provider = TrackedProvider(
            model=eval_model,
            api_key=api_key,
            provider=provider_name,
            base_url=base_url,
            verify_ssl=verify_ssl,
        )
        self.eval_model = eval_model

    def evaluate(self, task: Task, work_output: str) -> tuple[float, float, str]:
        """
        Evaluate work quality.

        Returns: (quality_score, eval_cost, reasoning)
        """
        if not work_output or len(work_output.strip()) < 50:
            return 0.0, 0.0, "Output too short or empty — skipping evaluation"

        # Don't evaluate obvious error messages
        stripped = work_output.strip().lower()
        if stripped.startswith("error:") or stripped.startswith("traceback"):
            return 0.0, 0.0, "Output is an error message — skipping evaluation"

        prompt = EVAL_PROMPT.format(
            sector=task.sector,
            occupation=task.occupation,
            deliverable_type=task.deliverable_type,
            prompt=task.prompt,
            output=work_output[:8000],  # Truncate to control eval cost
        )

        try:
            result = self.provider.chat(
                prompt=prompt,
                system=EVAL_SYSTEM,
                temperature=0.1,
                max_tokens=256,
            )

            # Parse JSON response
            text = result.content.strip()
            # Handle markdown code blocks
            if "```" in text:
                text = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                text = text.group(1) if text else result.content

            parsed = json.loads(text)
            score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
            reasoning = parsed.get("reasoning", "")

            return score, result.cost, reasoning

        except (json.JSONDecodeError, Exception) as e:
            # Fallback: try to extract a number
            try:
                numbers = re.findall(r"0\.\d+", result.content)
                if numbers:
                    return (
                        float(numbers[0]),
                        result.cost,
                        f"Parsed from text (error: {e})",
                    )
            except Exception:
                pass
            # Use actual cost from provider (not hardcoded) — $0 for local models
            fallback_cost = getattr(result, "cost", 0.0) if "result" in dir() else 0.0
            return 0.5, fallback_cost, f"Evaluation error: {e}"

    @property
    def total_eval_cost(self) -> float:
        return self.provider.usage.total_cost
