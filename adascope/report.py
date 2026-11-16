"""Report: render a stored Run as text.

Pure function of the stored run plus static profile and rules. Reads no live
source, so rendering the same file twice is byte-identical.

Every non-empty line ends with one of four labels: ``(measured)``,
``(derived)``, ``(hypothesis)`` or ``(unavailable)``. A number the run does not
carry is never estimated: it is reported as unavailable, with the reason. A
rule whose declared evidence resolves to nothing -- a typo in the rule data, or
a series this run does not carry -- gets a ``Warn:`` line naming the rule and
the id, rather than a hypothesis with no basis line and no hint of why.
"""

from __future__ import annotations

from .analyze import (
    EVIDENCE_FACTS,
    facts_from_run,
    hypotheses_from_run,
    observations_from_run,
    references_from_run,
)
from .model import Run

MEASURED_FORMS = (
    ("power_draw_mean_w", "power_draw_w"),
    ("power_draw_max_w", "power_draw_w"),
    ("temp_max_c", "temp_c"),
)


def _objective(run: Run) -> str:
    """The objective dict as one line. A missing key prints unknown."""
    objective = run.workload.objective if isinstance(run.workload.objective, dict) else {}
    text = f"{objective.get('metric', 'unknown')} ({objective.get('direction', 'unknown')})"
    target = objective.get("target")
    if target is not None:
        text += f" target {target}"
    return text


def _evidence_value(evidence_id: str, observations_by_id: dict, facts: dict):
    """The number a declared evidence id resolves to, or None.

    One place decides what "resolves" means, so the Basis line and the warning
    below cannot disagree: a measured summary resolves to its observation, a
    derived fact resolves to the value ``facts`` carries for it, and anything
    else resolves to nothing.
    """
    observation = observations_by_id.get(evidence_id)
    if observation is not None:
        return observation.value
    if evidence_id in EVIDENCE_FACTS:
        value = facts.get(evidence_id)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _basis_line(evidence_id: str, observations_by_id: dict, facts: dict) -> str:
    """One hypothesis's evidence, labeled by where the number came from.

    A summary of a measured series prints ``(measured)``; a derived fact (a
    rate, a ratio) prints ``(derived)``, the same label the number carries in
    the Derived block above.
    """
    observation = observations_by_id.get(evidence_id)
    if observation is not None:
        parts = [observation.metric, f"{observation.value:.1f}", observation.unit]
        return "     Basis: " + " ".join(p for p in parts if p) + " (measured)"
    value = _evidence_value(evidence_id, observations_by_id, facts)
    if value is not None:
        parts = [evidence_id, f"{value:.1f}", EVIDENCE_FACTS[evidence_id]]
        return "     Basis: " + " ".join(p for p in parts if p) + " (derived)"
    return f"     Basis: {evidence_id} unavailable in this run  (unavailable)"


def _unresolved_evidence(rule: dict, observations_by_id: dict, facts: dict) -> list[str]:
    """Declared evidence ids that resolve to nothing in this run.

    The analyser keeps only the ids that resolve, so a rule that names an id
    nothing produces -- a one-character typo in the rule data, or a series this
    run does not carry -- otherwise renders a hypothesis with no basis line and
    no hint as to why. These are what the warning names.
    """
    if not isinstance(rule, dict):
        return []
    declared = rule.get("evidence_observations", [])
    if not isinstance(declared, list):
        return []
    return [m for m in declared if _evidence_value(m, observations_by_id, facts) is None]


def _sampling(run: Run) -> str:
    sampling = run.sampling if isinstance(run.sampling, dict) else {}
    interval = sampling.get("interval_ms", "unknown")
    duration = sampling.get("duration_s")
    duration_text = f"{float(duration):.1f}" if isinstance(duration, (int, float)) else "unknown"
    samples = max((len(s.samples) for s in run.series), default=0)
    return f"{samples} at {interval} ms over {duration_text} s"


def render(run: Run, profile: dict, rules: list[dict]) -> str:
    facts = facts_from_run(run, profile)
    observations = observations_from_run(run)
    references = references_from_run(run, profile)
    hypotheses = hypotheses_from_run(run, profile, rules)
    by_metric = {s.metric: s.samples for s in run.series}
    observations_by_id = {o.metric: o for o in observations}
    rules_by_id = {rule["id"]: rule for rule in rules}

    hw = run.hardware
    wl = run.workload
    lines = [
        f"Run:         {run.id}  ({run.started_at} -> {run.ended_at})  (measured)",
        f"Workload:    {_objective(run)}  (measured)",
        f"Engine:      {wl.engine_id} via {wl.adapter_id} model {wl.model_id or 'unknown'}  (measured)",
        f"GPU:         {hw.name} ({hw.arch}, cc {hw.compute_capability}) "
        f"driver {hw.driver_version} CUDA {hw.cuda_driver_version}  (measured)",
        f"Tier:        {', '.join(run.sources) if run.sources else 'unknown'}  (measured)",
        f"Samples:     {_sampling(run)}  (measured)",
    ]

    lines.append("")
    lines.append("Measured:  (measured)")
    for metric, source_series in MEASURED_FORMS:
        observation = observations_by_id.get(metric)
        if observation is None:
            lines.append(f"  Unavailable: {metric} - the run has no {source_series} series  (unavailable)")
            continue
        lines.append(
            f"  {observation.metric:<22} {observation.value:.1f} {observation.unit}  "
            f"{observation.comparison}  {observation.method}  (measured)"
        )

    has_counters = "tokens_predicted_total" in by_metric and "tokens_predicted_seconds_total" in by_metric
    has_drafts = "draft_tokens_total" in by_metric and "draft_accepted_tokens_total" in by_metric
    ceiling_available = bool(facts["reference_ceiling_available"])

    lines.append("")
    lines.append("Derived:  (derived)")
    if facts["decode_rate_available"]:
        lines.append(f"  {'decode_rate_tok_s':<22} {facts['decode_rate_tok_s']:.1f} tok/s  "
                     f"{facts['decode_rate_method']}  (derived)")
    elif has_counters:
        lines.append("  Unavailable: decode_rate_tok_s - the counter series carry no delta over the "
                     "steady window  (unavailable)")
    else:
        lines.append("  Unavailable: decode_rate_tok_s - the run has no tokens_predicted_total and "
                     "tokens_predicted_seconds_total series  (unavailable)")
    lines.append(f"  {'spec_tokens_per_forward':<22} {facts['spec_tokens_per_forward']:.2f}  "
                 f"{facts['spec_method']}  (derived)")
    if has_drafts:
        lines.append(f"  {'spec_acceptance_ratio':<22} {facts['spec_acceptance_ratio']:.2f}  "
                     f"delta(draft_accepted_tokens_total)/delta(draft_tokens_total): acceptance, not "
                     f"tokens per forward pass  (derived)")
    else:
        lines.append("  Unavailable: spec_acceptance_ratio - the run has no draft_tokens_total and "
                     "draft_accepted_tokens_total series  (unavailable)")
    if ceiling_available:
        reference = references[0]
        lines.append(f"  {'reference ceiling':<22} {reference.ceiling:.1f} {reference.objective_unit}  "
                     f"{reference.workload_class}, limiting resource {reference.limiting_resource}, "
                     f"{reference.derivation['inputs']['bandwidth_gbps']:.0f} GB/s, "
                     f"{reference.derivation['inputs']['artifact_bytes']} B  (derived)")
    else:
        lines.append("  Unavailable: reference ceiling - the run records no artifact_bytes  (unavailable)")
    if "power_draw_w" in by_metric:
        lines.append(f"  {'power_ratio':<22} {facts['power_ratio']:.2f}  "
                     f"mean power over the steady window / limit  (derived)")
    else:
        lines.append("  Unavailable: power_ratio - the run has no power_draw_w series  (unavailable)")
    if facts["objective_ratio_available"]:
        lines.append(f"  {'objective_ratio':<22} {facts['objective_ratio']:.2f}  "
                     f"decode rate / ceiling  (derived)")
    else:
        lines.append("  Unavailable: objective_ratio - it needs both the decode rate and the ceiling "
                     "  (unavailable)")
    if not facts["model_consistent"]:
        lines.append(f"  Note: objective_ratio {facts['objective_ratio']:.2f} exceeds 1.0; the reference "
                     f"model under-predicts this run, so no near-roof claim is made  (derived)")

    lines.append("")
    if facts["engine_request_rate_tok_s"] is None:
        lines.append("Engine's own per-request rate: unavailable - the run has no request_decode_* "
                     "series  (unavailable)")
    else:
        lines.append(f"Engine's own per-request rate: {facts['engine_request_rate_tok_s']:.1f} tok/s over "
                     f"{facts['engine_request_count']} requests, {facts['engine_request_method']}  (measured)")

    lines.append("")
    if hypotheses:
        lines.append("Hypotheses (ranked):  (hypothesis)")
        for index, hypothesis in enumerate(hypotheses):
            letter = chr(ord("A") + index)
            rule_id = hypothesis.rules[0] if hypothesis.rules else hypothesis.id
            lines.append(f"  {letter}  {rule_id}  {hypothesis.claim}  ({hypothesis.confidence.value})")
            for evidence_id in hypothesis.evidence:
                lines.append(_basis_line(evidence_id, observations_by_id, facts))
            for evidence_id in _unresolved_evidence(rules_by_id.get(rule_id, {}),
                                                    observations_by_id, facts):
                lines.append(f"     Warn: {rule_id} declares evidence {evidence_id!r}, which resolves "
                             f"to neither an observation nor a derived fact in this run  "
                             f"(unavailable)")
            if hypothesis.alternatives:
                alternatives = ", ".join(
                    f"{h.rules[0] if h.rules else h.id} ({h.confidence.value})" for h in hypothesis.alternatives
                )
                lines.append(f"     Alternatives: {alternatives}")
    else:
        lines.append("Hypothesis:  none fired; no limiting resource identified  (hypothesis)")

    lines.append("")
    lines.append("Status:      preliminary diagnosis  (derived)")
    lines.append("Confidence:  unconfirmed until the experiment completes.  (hypothesis)")
    return "\n".join(lines) + "\n"
