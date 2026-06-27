"""Keyless tests — everything here runs in replay mode with no API key.

Covers: case parsing/validation, score aggregation + threshold gating, the
judge's robustness to malformed verdicts, and a full replay pipeline over the
committed cases and fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.schema import (
    Case,
    CaseError,
    Criterion,
    CriterionScore,
    JudgeVerdict,
    load_cases,
    parse_case,
)
from harness.judge import _parse_verdict
from harness.score import aggregate, evaluate_case, results_to_dict

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
FIXTURES_DIR = ROOT / "fixtures"


# --------------------------------------------------------------------------- #
# Schema / case loading                                                       #
# --------------------------------------------------------------------------- #

def _minimal_case_dict() -> dict:
    return {
        "id": "demo",
        "task": "Do the thing.",
        "rubric": [{"id": "a", "description": "criterion a", "weight": 2}],
        "threshold": 0.5,
    }


def test_parse_case_valid():
    case = parse_case(_minimal_case_dict())
    assert case.id == "demo"
    assert case.criterion_ids == ("a",)
    assert case.rubric[0].weight == 2.0
    assert case.threshold == 0.5


def test_parse_case_missing_task_raises():
    data = _minimal_case_dict()
    del data["task"]
    with pytest.raises(CaseError, match="missing required field 'task'"):
        parse_case(data)


def test_parse_case_empty_rubric_raises():
    data = _minimal_case_dict()
    data["rubric"] = []
    with pytest.raises(CaseError, match="non-empty list"):
        parse_case(data)


def test_parse_case_duplicate_criterion_raises():
    data = _minimal_case_dict()
    data["rubric"] = [
        {"id": "a", "description": "x"},
        {"id": "a", "description": "y"},
    ]
    with pytest.raises(CaseError, match="duplicate criterion id"):
        parse_case(data)


def test_parse_case_bad_threshold_raises():
    data = _minimal_case_dict()
    data["threshold"] = 1.5
    with pytest.raises(CaseError, match=r"within \[0, 1\]"):
        parse_case(data)


def test_load_cases_finds_all_three():
    cases = load_cases(CASES_DIR)
    ids = {c.id for c in cases}
    assert ids == {"receipt-extract", "constrained-summary", "slugify-spec"}


# --------------------------------------------------------------------------- #
# Scoring + threshold gating                                                  #
# --------------------------------------------------------------------------- #

def _case_with_weights(weights: dict[str, float], threshold: float = 0.8) -> Case:
    return Case(
        id="t",
        description="",
        task="x",
        rubric=tuple(
            Criterion(cid, f"crit {cid}", w) for cid, w in weights.items()
        ),
        threshold=threshold,
    )


def _verdict(scores: dict[str, float]) -> JudgeVerdict:
    return JudgeVerdict(
        scores=tuple(CriterionScore(cid, s, "") for cid, s in scores.items()),
        summary="",
    )


def test_aggregate_is_weighted_mean():
    case = _case_with_weights({"a": 1, "b": 3})
    # a=1.0, b=0.0 -> (1*1 + 3*0) / 4 = 0.25
    result = aggregate(case, "cand", _verdict({"a": 1.0, "b": 0.0}))
    assert result.weighted_score == pytest.approx(0.25)
    assert result.passed is False


def test_threshold_gating_boundary():
    case = _case_with_weights({"a": 1}, threshold=0.8)
    assert aggregate(case, "c", _verdict({"a": 0.8})).passed is True   # == passes
    assert aggregate(case, "c", _verdict({"a": 0.79})).passed is False


def test_aggregate_zero_weight_raises():
    case = _case_with_weights({"a": 0})
    with pytest.raises(ValueError, match="weight must be positive"):
        aggregate(case, "c", _verdict({"a": 1.0}))


# --------------------------------------------------------------------------- #
# Judge verdict parsing robustness                                            #
# --------------------------------------------------------------------------- #

def test_judge_clamps_out_of_range_scores():
    case = _case_with_weights({"a": 1, "b": 1})
    verdict = _parse_verdict(
        {"criteria": [{"id": "a", "score": 1.7}, {"id": "b", "score": -0.5}],
         "summary": "s"},
        case,
    )
    assert verdict.score_for("a") == 1.0
    assert verdict.score_for("b") == 0.0


def test_judge_missing_criterion_defaults_to_zero():
    case = _case_with_weights({"a": 1, "b": 1})
    verdict = _parse_verdict({"criteria": [{"id": "a", "score": 1.0}], "summary": ""}, case)
    assert verdict.score_for("b") == 0.0


# --------------------------------------------------------------------------- #
# Full replay pipeline (no API key)                                           #
# --------------------------------------------------------------------------- #

def test_replay_pipeline_all_cases_pass():
    cases = load_cases(CASES_DIR)
    results = [
        evaluate_case(c, live=False, fixtures_dir=str(FIXTURES_DIR)) for c in cases
    ]
    assert all(r.passed for r in results), {
        r.case_id: r.weighted_score for r in results
    }
    report = results_to_dict(results)
    assert report["summary"]["failed"] == 0
    assert report["summary"]["cases"] == 3


def test_replay_missing_fixture_raises(tmp_path):
    cases = load_cases(CASES_DIR)
    with pytest.raises(FileNotFoundError, match="no recorded candidate"):
        evaluate_case(cases[0], live=False, fixtures_dir=str(tmp_path))
