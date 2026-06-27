"""Model selection for live mode.

Defaults follow current Anthropic guidance (Claude Opus 4.8); override per run
with EVAL_TARGET_MODEL / EVAL_JUDGE_MODEL. Centralized here so model IDs live in
exactly one place rather than scattered through the runner and judge.
"""

from __future__ import annotations

import os

# Current default model. Bump here when migrating; nothing else hardcodes an ID.
DEFAULT_MODEL = "claude-opus-4-8"


def resolve_target_model() -> str:
    """The model under evaluation."""
    return os.environ.get("EVAL_TARGET_MODEL", DEFAULT_MODEL)


def resolve_judge_model() -> str:
    """The model acting as judge."""
    return os.environ.get("EVAL_JUDGE_MODEL", DEFAULT_MODEL)
