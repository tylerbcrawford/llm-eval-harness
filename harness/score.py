"""Aggregate a judge verdict into a weighted score and a pass/fail.

The aggregate is a weighted mean of the per-criterion scores, where the weights
come from the rubric. A case passes when its aggregate clears the case's
``threshold``. This module is deliberately pure and import-light so the scoring
logic can be unit-tested without any model call.
"""

from __future__ import annotations

from .schema import Case, JudgeVerdict, Result
from . import runner, judge as judge_mod


def aggregate(case: Case, candidate: str, verdict: JudgeVerdict) -> Result:
    """Combine a verdict into a single weighted score and pass/fail."""
    total_weight = sum(c.weight for c in case.rubric)
    if total_weight <= 0:
        raise ValueError(f"case {case.id!r}: total rubric weight must be positive")

    weighted = sum(verdict.score_for(c.id) * c.weight for c in case.rubric)
    score = weighted / total_weight

    return Result(
        case_id=case.id,
        candidate=candidate,
        verdict=verdict,
        weighted_score=score,
        threshold=case.threshold,
        passed=score >= case.threshold,
    )


def evaluate_case(
    case: Case,
    *,
    live: bool | None = None,
    record: bool = False,
    fixtures_dir: str = "fixtures",
) -> Result:
    """Full pipeline for one case: run the target, judge it, aggregate."""
    candidate = runner.run(
        case, live=live, record=record, fixtures_dir=fixtures_dir
    )
    verdict = judge_mod.judge(
        case, candidate, live=live, record=record, fixtures_dir=fixtures_dir
    )
    return aggregate(case, candidate, verdict)


def result_to_dict(result: Result) -> dict:
    """JSON-serializable view of a result (for results.json)."""
    return {
        "case_id": result.case_id,
        "weighted_score": round(result.weighted_score, 4),
        "threshold": result.threshold,
        "passed": result.passed,
        "criteria": [
            {"id": s.id, "score": s.score, "reasoning": s.reasoning}
            for s in result.verdict.scores
        ],
        "summary": result.verdict.summary,
    }


def results_to_dict(results: list[Result]) -> dict:
    """Aggregate report across all cases."""
    passed = sum(1 for r in results if r.passed)
    return {
        "summary": {
            "cases": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "mean_score": (
                round(sum(r.weighted_score for r in results) / len(results), 4)
                if results
                else 0.0
            ),
        },
        "results": [result_to_dict(r) for r in results],
    }
