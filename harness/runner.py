"""Run the *target* model on a case to produce a candidate answer.

Two paths, one interface:

* **replay** (default): read ``fixtures/<case-id>/candidate.txt``. No API key,
  no network, fully deterministic — this is what makes the repo clone-and-run.
* **live** (``EVAL_LIVE=1`` or ``--record``): call the real Anthropic API.

The ``anthropic`` SDK is imported lazily inside the live path so that replay mode
never needs it installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import resolve_target_model
from .schema import Case

CANDIDATE_FILE = "candidate.txt"


def _fixture_path(fixtures_dir: str | Path, case_id: str) -> Path:
    return Path(fixtures_dir) / case_id / CANDIDATE_FILE


def _read_fixture(fixtures_dir: str | Path, case_id: str) -> str:
    path = _fixture_path(fixtures_dir, case_id)
    if not path.exists():
        raise FileNotFoundError(
            f"no recorded candidate for case {case_id!r} at {path}. "
            f"Run with --record (and EVAL_LIVE=1 + a key) to capture it."
        )
    return path.read_text(encoding="utf-8")


def _call_target_live(case: Case) -> str:
    from anthropic import Anthropic  # lazy: only needed in live mode

    client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    kwargs: dict = {
        "model": resolve_target_model(),
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": case.task}],
    }
    if case.target_system:
        kwargs["system"] = case.target_system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def run(
    case: Case,
    *,
    live: bool | None = None,
    record: bool = False,
    fixtures_dir: str | Path = "fixtures",
) -> str:
    """Return the target model's candidate answer for *case*.

    ``live`` defaults to the ``EVAL_LIVE`` environment variable. ``record`` forces
    a live call and writes the result to the fixture for future replay.
    """
    if live is None:
        live = os.environ.get("EVAL_LIVE", "0") not in ("", "0", "false", "False")

    if not (live or record):
        return _read_fixture(fixtures_dir, case.id)

    candidate = _call_target_live(case)

    if record:
        path = _fixture_path(fixtures_dir, case.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(candidate + "\n", encoding="utf-8")

    return candidate
