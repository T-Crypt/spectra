"""Local AI assistance (Phase 5), optional.

A local model may draft hypotheses and summarize reports. Its output is
always labeled as a hypothesis and is never the source of a benchmark
conclusion: the deterministic engine and the stored runs remain authoritative.
The module degrades to a deterministic template when no model endpoint is
reachable, so it never blocks the pipeline.
"""

from __future__ import annotations

from typing import Any, Callable

from .model import Hypothesis, Quality


def draft_hypotheses(
    run_id: str,
    facts: dict[str, Any],
    model_call: Callable[[str], str] | None = None,
) -> list[Hypothesis]:
    """Draft hypothesis objects from facts. Always confidence=hypothesis."""
    prompts = _prompt(facts)
    drafts: list[Hypothesis] = []
    for index, claim in enumerate(_claims(facts)):
        text = claim
        if model_call is not None:
            try:
                text = model_call(prompts[index])
            except Exception:
                text = claim
        drafts.append(Hypothesis(
            id=f"h-draft-{run_id}-{index}",
            run_id=run_id,
            claim=text,
            mechanism="drafted by local assistance; unverified",
            rank_score=0.0,
            evidence=[],
            rules=[],
            alternatives=[],
            confidence=Quality.HYPOTHESIS,
        ))
    return drafts


def summarize_report(text: str, model_call: Callable[[str], str] | None = None) -> str:
    """Summarize a report. Falls back to a one-line deterministic summary."""
    if model_call is not None:
        try:
            return model_call("Summarize this report in one sentence: " + text)
        except Exception:
            pass
    # Deterministic fallback: first non-empty line.
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "no report content"


def _claims(facts: dict[str, Any]) -> list[str]:
    claims = []
    if facts.get("co_tenant"):
        claims.append("a co-tenant may have contaminated the run")
    if facts.get("power_ratio", 0) >= 0.95:
        claims.append("power cap may be limiting throughput")
    if not claims:
        claims.append("no limiting resource identified from the available evidence")
    return claims


def _prompt(facts: dict[str, Any]) -> list[str]:
    return [f"Given facts {facts}, draft a hypothesis" for _ in _claims(facts)]
