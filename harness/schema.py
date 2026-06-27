"""Typed data model + YAML case loader.

A *case* is a task plus a rubric. The runner produces a *candidate* (the target
model's answer); the judge produces a *verdict* (a per-criterion score); the
scorer aggregates the verdict into a weighted result and a pass/fail against the
case's threshold.

Everything downstream depends only on these dataclasses, so the wire formats
(YAML on disk, JSON fixtures) are parsed/validated here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class CaseError(ValueError):
    """A case file is malformed (missing field, bad type, duplicate id)."""


@dataclass(frozen=True)
class Criterion:
    """One gradeable rubric line. ``weight`` scales its contribution."""

    id: str
    description: str
    weight: float = 1.0


@dataclass(frozen=True)
class Case:
    """A task + rubric. ``threshold`` is the min weighted score (0..1) to pass."""

    id: str
    description: str
    task: str
    rubric: tuple[Criterion, ...]
    threshold: float = 0.8
    target_system: str | None = None

    @property
    def criterion_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.rubric)


@dataclass(frozen=True)
class CriterionScore:
    """The judge's score (0..1) and reasoning for one criterion."""

    id: str
    score: float
    reasoning: str


@dataclass(frozen=True)
class JudgeVerdict:
    """The judge's full assessment of a candidate against a rubric."""

    scores: tuple[CriterionScore, ...]
    summary: str

    def score_for(self, criterion_id: str) -> float:
        for s in self.scores:
            if s.id == criterion_id:
                return s.score
        raise KeyError(f"judge returned no score for criterion {criterion_id!r}")


@dataclass(frozen=True)
class Result:
    """A scored case: the weighted aggregate and whether it cleared threshold."""

    case_id: str
    candidate: str
    verdict: JudgeVerdict
    weighted_score: float
    threshold: float
    passed: bool


# --------------------------------------------------------------------------- #
# Loading + validation                                                        #
# --------------------------------------------------------------------------- #

def _require(mapping: dict, key: str, where: str) -> object:
    if key not in mapping:
        raise CaseError(f"{where}: missing required field {key!r}")
    return mapping[key]


def parse_case(data: dict, *, source: str = "<dict>") -> Case:
    """Validate a parsed-YAML mapping into a :class:`Case`."""
    if not isinstance(data, dict):
        raise CaseError(f"{source}: expected a mapping at the top level")

    case_id = _require(data, "id", source)
    raw_rubric = _require(data, "rubric", source)
    if not isinstance(raw_rubric, list) or not raw_rubric:
        raise CaseError(f"{source}: 'rubric' must be a non-empty list")

    criteria: list[Criterion] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_rubric):
        where = f"{source}: rubric[{i}]"
        if not isinstance(item, dict):
            raise CaseError(f"{where}: expected a mapping")
        cid = str(_require(item, "id", where))
        if cid in seen:
            raise CaseError(f"{where}: duplicate criterion id {cid!r}")
        seen.add(cid)
        criteria.append(
            Criterion(
                id=cid,
                description=str(_require(item, "description", where)),
                weight=float(item.get("weight", 1.0)),
            )
        )

    threshold = float(data.get("threshold", 0.8))
    if not 0.0 <= threshold <= 1.0:
        raise CaseError(f"{source}: 'threshold' must be within [0, 1]")

    return Case(
        id=str(case_id),
        description=str(data.get("description", "")),
        task=str(_require(data, "task", source)),
        rubric=tuple(criteria),
        threshold=threshold,
        target_system=(
            str(data["target_system"]) if data.get("target_system") else None
        ),
    )


def load_case(path: str | Path) -> Case:
    """Load and validate a single case YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return parse_case(data, source=str(path))


def load_cases(directory: str | Path) -> list[Case]:
    """Load every ``*.yaml`` case in *directory*, sorted by id for stable runs."""
    directory = Path(directory)
    cases = [load_case(p) for p in sorted(directory.glob("*.yaml"))]
    if not cases:
        raise CaseError(f"no *.yaml cases found in {directory}")
    ids = [c.id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise CaseError(f"duplicate case ids across files: {sorted(dupes)}")
    return cases
