"""A small, transparent LLM-as-judge evaluation harness.

Runs fully offline in replay mode (reads recorded fixtures, needs no API key);
set EVAL_LIVE=1 to run against the real Anthropic API instead.
"""

__version__ = "0.1.0"
