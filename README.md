# llm-eval-harness

[![eval](https://github.com/tylerbcrawford/llm-eval-harness/actions/workflows/eval.yml/badge.svg)](https://github.com/tylerbcrawford/llm-eval-harness/actions/workflows/eval.yml)

A small, transparent **LLM-as-judge** evaluation harness. You define eval cases
(a task + a rubric), a target model answers, and a second model — the *judge* —
scores each answer against the rubric. Scores aggregate to a weighted pass/fail
that a CI pipeline can gate on.

**It runs fully offline.** By default the harness replays recorded model
responses from `fixtures/`, so you can clone it and run the whole suite —
`pytest` and the scored report — with **no API key and no network**. Set
`EVAL_LIVE=1` to run the same cases against the real Anthropic API.

```text
case                 score  thresh  result
------------------------------------------
constrained-summary  1.00   0.80    PASS
receipt-extract      1.00   0.85    PASS
slugify-spec         1.00   0.85    PASS
------------------------------------------
3/3 passed   mean 1.00
```

## Why a judge instead of string matching

Most useful model outputs can't be graded with `==`. Consider the bundled
`receipt-extract` case, which asks the model to pull a vendor name out of a
receipt. Real Claude returned:

```json
{"vendor": "BLUE BOTTLE COFFEE", "date": "2026-03-14", "total": 10.58}
```

A string check against `"Blue Bottle Coffee"` would mark that **wrong** over
letter casing. The rubric criterion is *"vendor matches, case-insensitive and
whitespace-normalized,"* and the judge scores it correctly — with its reasoning
recorded in the fixture:

> *"Vendor is 'BLUE BOTTLE COFFEE' which matches case-insensitive and
> whitespace-normalized."*

That's the niche LLM-as-judge fills: grading **semantic** criteria (faithfulness,
"under 30 words and mentions both facts," "meets the spec") that brittle exact
matching can't express. It's a publicly documented evaluation technique — this
repo is a clean, runnable demonstration of it.

## Quickstart

```bash
git clone https://github.com/tylerbcrawford/llm-eval-harness
cd llm-eval-harness
pip install -e ".[dev]"

python -m harness run cases/   # replay mode — no key, no network
pytest -q                      # the same pipeline, asserted
```

Both commands work on a fresh clone with no configuration. The eval run writes a
machine-readable report to `results.json` and exits non-zero if any case falls
below its threshold, so it gates a CI job directly.

## How it works

```text
case.yaml ─► runner ─► candidate ─► judge(task, rubric, candidate) ─► verdict ─► score ─► results.json
            (target)   (answer)     (LLM-as-judge, structured output)  (0..1 each)  (weighted)   + pass/fail
```

1. **Case** (`cases/*.yaml`) — a task prompt plus a weighted rubric and a pass
   threshold.
2. **Runner** (`harness/runner.py`) — gets the target model's answer (the
   *candidate*).
3. **Judge** (`harness/judge.py`) — scores the candidate against each rubric
   criterion (0.0–1.0) with reasoning. In live mode the judge call uses
   **structured outputs** so the verdict is guaranteed to validate against a
   fixed JSON schema — the model can't return malformed scoring.
4. **Score** (`harness/score.py`) — a weighted mean of the criterion scores,
   compared to the case threshold.

## Replay vs. live

| Mode | Trigger | Needs a key? | What it does |
|------|---------|--------------|--------------|
| **Replay** (default) | — | No | Runner and judge read recorded JSON from `fixtures/`. Deterministic; runs in CI on every push. |
| **Live** | `EVAL_LIVE=1` or `--live` | Yes (`ANTHROPIC_API_KEY`) | Runner and judge call the real Anthropic API. |
| **Record** | `--record` | Yes | Live-call and overwrite `fixtures/` with the captured candidate + verdict. |

```bash
# Live run against the real API
EVAL_LIVE=1 python -m harness run cases/ --live

# Re-record fixtures (e.g. after editing a case)
python -m harness run cases/ --record
```

The committed fixtures in this repo are **real recorded responses** from
`claude-opus-4-8`, captured with `--record`. Models default to `claude-opus-4-8`
for both target and judge; override with `EVAL_TARGET_MODEL` / `EVAL_JUDGE_MODEL`.

## The bundled cases

| Case | What it probes |
|------|----------------|
| `receipt-extract` | Structured JSON extraction from messy text; correct fields, valid JSON, no hallucinated values. |
| `constrained-summary` | A hard length limit **and** two required facts **and** faithfulness — a multi-constraint check a judge handles better than string matching. |
| `slugify-spec` | Implementing a small function to a written spec, including edge cases. |

Add your own by dropping a YAML file in `cases/` and recording its fixture.

## Project layout

```text
cases/                 # YAML: task + rubric + threshold
harness/
  schema.py            # dataclasses + YAML loader/validator
  config.py            # model selection (one place for model IDs)
  runner.py            # target model -> candidate (replay | live)
  judge.py             # LLM-as-judge -> per-criterion scores (replay | live)
  score.py             # aggregate -> results.json + pass/fail
  __main__.py          # CLI: python -m harness run cases/
fixtures/<case-id>/    # recorded candidate.txt + verdict.json (deterministic replay)
tests/                 # pytest: parsing, scoring, gating, full replay
.github/workflows/     # CI: replay gate on every push; optional live job
```

## Notes

Built with [Claude Code](https://claude.com/claude-code) — I designed the
harness and rubrics and directed the implementation. This is a personal project
demonstrating evaluation techniques; the cases are deliberately generic.

## License

[MIT](LICENSE)
