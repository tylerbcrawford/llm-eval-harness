"""LLM-as-judge: score a candidate against a rubric, one criterion at a time.

LLM-as-judge is a publicly documented evaluation technique (Anthropic and OpenAI
both publish on it). The judge is given the original task, the candidate answer,
and the rubric, and returns a 0..1 score plus reasoning for each criterion.

In live mode the judge call uses **structured outputs** (`output_config.format`)
so the returned verdict is guaranteed to validate against ``VERDICT_SCHEMA`` —
the model cannot hand back malformed scoring. Replay mode reads the same JSON
shape from ``fixtures/<case-id>/verdict.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import resolve_judge_model
from .schema import Case, CriterionScore, JudgeVerdict

VERDICT_FILE = "verdict.json"

JUDGE_SYSTEM = (
    "You are a rigorous evaluation judge. You score how well a candidate answer "
    "satisfies each criterion of a rubric, independently and without leniency. "
    "Judge only against the criteria given; do not invent new requirements."
)

# Structured-output schema for the verdict. Note: JSON-schema numeric bounds
# (minimum/maximum) are NOT supported by structured outputs, so scores are
# clamped to [0, 1] in code (see _parse_verdict).
VERDICT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": ["id", "score", "reasoning"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["criteria", "summary"],
    "additionalProperties": False,
}


def build_prompt(case: Case, candidate: str) -> str:
    """Render the judge prompt from a case and a candidate answer."""
    lines = [
        "Evaluate the CANDIDATE ANSWER against the RUBRIC below.",
        "",
        "TASK THAT WAS GIVEN TO THE MODEL:",
        case.task.strip(),
        "",
        "CANDIDATE ANSWER:",
        candidate.strip() or "(empty)",
        "",
        "RUBRIC — score each criterion from 0.0 (not met) to 1.0 (fully met):",
    ]
    for c in case.rubric:
        lines.append(f"- {c.id}: {c.description.strip()}")
    lines += [
        "",
        "Return one object per criterion with its id, a score in [0, 1], and a "
        "brief reasoning, plus a one-sentence overall summary. Score every "
        "criterion id listed above exactly once.",
    ]
    return "\n".join(lines)


def _parse_verdict(data: dict, case: Case) -> JudgeVerdict:
    """Turn raw verdict JSON (from the API or a fixture) into a JudgeVerdict.

    Robust to a judge that omits a criterion (defaults to 0.0) or returns an
    out-of-range score (clamped to [0, 1]).
    """
    by_id = {str(item["id"]): item for item in data.get("criteria", [])}
    scores: list[CriterionScore] = []
    for c in case.rubric:
        item = by_id.get(c.id)
        if item is None:
            scores.append(
                CriterionScore(c.id, 0.0, "judge returned no score for this criterion")
            )
            continue
        raw = float(item.get("score", 0.0))
        clamped = min(1.0, max(0.0, raw))
        scores.append(
            CriterionScore(c.id, clamped, str(item.get("reasoning", "")).strip())
        )
    return JudgeVerdict(scores=tuple(scores), summary=str(data.get("summary", "")).strip())


def _fixture_path(fixtures_dir: str | Path, case_id: str) -> Path:
    return Path(fixtures_dir) / case_id / VERDICT_FILE


def _read_fixture(fixtures_dir: str | Path, case_id: str) -> dict:
    path = _fixture_path(fixtures_dir, case_id)
    if not path.exists():
        raise FileNotFoundError(
            f"no recorded verdict for case {case_id!r} at {path}. "
            f"Run with --record (and EVAL_LIVE=1 + a key) to capture it."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _call_judge_live(case: Case, candidate: str) -> dict:
    from anthropic import Anthropic  # lazy: only needed in live mode

    client = Anthropic()
    resp = client.messages.create(
        model=resolve_judge_model(),
        max_tokens=4096,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": build_prompt(case, candidate)}],
        output_config={"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def judge(
    case: Case,
    candidate: str,
    *,
    live: bool | None = None,
    record: bool = False,
    fixtures_dir: str | Path = "fixtures",
) -> JudgeVerdict:
    """Score *candidate* against *case*'s rubric (replay or live)."""
    if live is None:
        live = os.environ.get("EVAL_LIVE", "0") not in ("", "0", "false", "False")

    if not (live or record):
        return _parse_verdict(_read_fixture(fixtures_dir, case.id), case)

    raw = _call_judge_live(case, candidate)

    if record:
        path = _fixture_path(fixtures_dir, case.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    return _parse_verdict(raw, case)
