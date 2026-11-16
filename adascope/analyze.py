"""Analysis: pure functions from a stored Run to ranked hypotheses.

Nothing here touches live sources. The store holds raw measurements. These
functions derive facts, observations, references, and hypotheses from the file
alone, so a report can be rebuilt byte-identically at any time.

Evidence ids. ``Hypothesis.evidence`` holds observation ids, per the frozen C2
type. Observations are computed at report time and never stored, and
``observations_from_run`` emits at most one observation per metric name, so an
observation's id is its ``metric``. A rule may also name one of the derived
facts in :data:`EVIDENCE_FACTS`, which are not observations because they are
ratios and model outputs rather than summaries of one measured series; the
renderer prints those basis lines under the derived label they already carry
in the report.

Labels. ``Observation`` carries no quality field, so this module emits measured
summaries only (a mean, a max, a span). Ratio-like and model-derived numbers
live in ``facts`` and are printed under a derived label by the renderer.
"""

from __future__ import annotations

from dataclasses import replace

from .engine import fires, rule_confidence
from .model import Hypothesis, Observation, Quality, ReferenceModel, Run
from .reference import dense_decode_reference

W_CONFIDENCE = 1.0
W_HEADROOM = 1.0

# Ranking weights are a judgement, not a measurement: they are named constants
# with a comment, and the eval's A4 rather than these numbers is what proves
# attribution. Phase 1 has no cost model, so MILESTONE-1's experiment-cost term
# is omitted rather than zero-weighted.
CONFIDENCE_WEIGHT = {
    Quality.MEASURED: 3.0,
    Quality.DERIVED: 1.0,
    Quality.HYPOTHESIS: 0.0,
}

SPEC_ROUND_METHOD = "committed/(committed-accepted): tokens per decode forward pass"
SPEC_ROUNDS_METHOD = "committed/draft_rounds_total: tokens per decode forward pass"
SPEC_NONE_METHOD = "no draft counters; no speculation assumed"
SPEC_JSONL_METHOD = "tokens/rounds from the request log: tokens per decode round"
REQUEST_RATE_METHOD = "delta(request_decode_tokens)/delta(request_decode_seconds), token-weighted"

# Derived facts a rule may name in ``evidence_observations``, with the unit the
# renderer prints beside them. A rule's declared evidence has to resolve to a
# labeled number the report can show, or the hypothesis renders with no basis
# at all; the roof rule names a rate, which is a delta ratio rather than the
# summary of one series and so is a fact, not an observation.
EVIDENCE_FACTS = {
    "decode_rate_tok_s": "tok/s",
    "reference_ceiling_tok_s": "tok/s",
    "engine_request_rate_tok_s": "tok/s",
    "objective_ratio": "",
    "power_ratio": "",
    "spec_tokens_per_forward": "",
    "spec_acceptance_ratio": "",
    "temp_c": "C",
    "host_exposed_ratio": "",
}
THROTTLE_FALLBACKS = (
    "throttle.sw_power_cap",
    "throttle.sw_thermal_slowdown",
    "throttle.hw_thermal_slowdown",
)


def _steady(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop the first 10 percent of samples as warmup. One rule, one place."""
    cut = len(samples) // 10
    return samples[cut:] if len(samples) > 1 else samples


def _by_metric(run: Run) -> dict[str, list[tuple[float, float]]]:
    return {s.metric: s.samples for s in run.series}


def _mean(points: list[tuple[float, float]]) -> float | None:
    vals = [v for _, v in points]
    return sum(vals) / len(vals) if vals else None


def _delta(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    return points[-1][1] - points[0][1]


def _span(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    return (points[0][0], points[-1][0])


def confidence_weight(quality: Quality) -> float:
    return CONFIDENCE_WEIGHT.get(Quality(quality), 0.0)


def spec_tokens_per_forward(by_metric: dict[str, list[tuple[float, float]]]) -> tuple[float, str]:
    """Tokens committed per decode forward pass, derived from the counters.

    Every decode round commits ``1 + accepted_i`` tokens, so
    ``committed = sum(accepted_i + 1) = accepted + rounds`` and
    ``rounds = committed - accepted``. Tokens per forward pass is therefore
    ``committed / (committed - accepted)``. An engine that publishes a rounds
    counter (llama.cpp's ``spec_decode_num_drafts_total``, stored as
    ``draft_rounds_total``) gives the rounds directly, and
    ``committed / rounds`` replaces the subtraction. A rounds counter that
    disagrees with committed (more rounds than committed tokens) is
    inconsistent data and falls through to the next source rather than
    dividing into nonsense.

    The alternative seen in the predecessor code, ``1 + accepted / drafted``,
    divides accepted drafts by drafted tokens instead of by rounds, and it puts
    the recorded rate above the ceiling it implies; see docs/EVAL.md A9.
    """
    committed = _delta(_steady(by_metric.get("tokens_predicted_total", [])))
    rounds = _delta(_steady(by_metric.get("draft_rounds_total", [])))
    if rounds and committed is not None and 0 < rounds <= committed:
        return committed / rounds, SPEC_ROUNDS_METHOD
    accepted = _delta(_steady(by_metric.get("draft_accepted_tokens_total", [])))
    if not accepted or committed is None or accepted >= committed:
        return 1.0, SPEC_NONE_METHOD
    return committed / (committed - accepted), SPEC_ROUND_METHOD


def facts_from_run(run: Run, profile: dict) -> dict:
    """Every labeled fact the rules and the renderer read."""
    series = _by_metric(run)
    power = _steady(series.get("power_draw_w", []))
    power_mean = _mean(power)
    limit = run.hardware.power_limit_w
    power_ratio = (power_mean / limit) if power_mean is not None and limit else 0.0

    tokens = _steady(series.get("tokens_predicted_total", []))
    seconds = _steady(series.get("tokens_predicted_seconds_total", []))
    tok_delta = _delta(tokens)
    sec_delta = _delta(seconds)
    wall_span = (power[-1][0] - power[0][0]) if len(power) >= 2 else 0.0

    request_tokens = _steady(series.get("request_decode_tokens", []))
    request_seconds = _steady(series.get("request_decode_seconds", []))
    request_rounds = _steady(series.get("request_decode_rounds", []))
    request_tokens_delta = _delta(request_tokens) if len(request_tokens) >= 2 else None
    request_seconds_delta = _delta(request_seconds) if len(request_seconds) >= 2 else None
    request_rounds_delta = _delta(request_rounds) if len(request_rounds) >= 2 else None
    request_rate_available = bool(
        request_tokens_delta and request_seconds_delta and request_seconds_delta > 0)
    request_rate = (request_tokens_delta / request_seconds_delta) if request_rate_available else 0.0
    request_tpr_available = bool(
        request_tokens_delta and request_rounds_delta and request_rounds_delta > 0)
    request_tpr = (request_tokens_delta / request_rounds_delta) if request_tpr_available else 0.0

    if tok_delta is not None and sec_delta:
        decode_rate = tok_delta / sec_delta
        rate_method = "delta(tokens_predicted_total)/delta(tokens_predicted_seconds_total)"
        rate_available = True
    elif tok_delta is not None and wall_span > 0:
        decode_rate = tok_delta / wall_span
        rate_method = "delta(tokens_predicted_total)/wall_window"
        rate_available = True
    elif request_rate_available:
        # No engine counters in this run -- the v3 binary in service exposes no
        # /metrics -- so the request log's own token-weighted rate stands in,
        # labeled with its method. A run with neither keeps the sentinel.
        decode_rate = request_rate
        rate_method = REQUEST_RATE_METHOD
        rate_available = True
    else:
        # The sentinel the plan mandates in facts. ``decode_rate_available`` is
        # what tells the renderer not to print it as a derived measurement: a
        # series with a single sample has no delta, so this run has no rate.
        decode_rate = 0.0
        rate_method = "no engine counters; rate unknown"
        rate_available = False

    spec_factor, spec_method = spec_tokens_per_forward(series)
    if spec_method == SPEC_NONE_METHOD and request_tpr_available and request_tpr > 1.0:
        # Same quantity as the counter derivation -- committed tokens per
        # decode round -- read from the request log when the engine exposes no
        # draft counters. Counters win whenever they exist.
        spec_factor, spec_method = request_tpr, SPEC_JSONL_METHOD
    drafted = _delta(_steady(series.get("draft_tokens_total", [])))
    accepted = _delta(_steady(series.get("draft_accepted_tokens_total", [])))
    acceptance = (accepted / drafted) if drafted and accepted is not None else 0.0

    bandwidth = float(profile.get("mem_bandwidth_spec_gbps", 1008.0))
    artifact_bytes = run.workload.artifact_bytes
    ceiling_available = bool(artifact_bytes)
    if ceiling_available:
        ceiling = dense_decode_reference(
            artifact_bytes=int(artifact_bytes),
            bandwidth_gbps=bandwidth,
            spec_tokens_per_forward=spec_factor,
        ).ceiling
    else:
        ceiling = 0.0
    # A ratio needs both halves. When either is missing it stays the 0.0
    # sentinel, and ``objective_ratio_available`` is what tells a consumer --
    # the renderer and the ranking both read it -- not to use that 0.0.
    objective_ratio_available = rate_available and ceiling_available
    objective_ratio = (decode_rate / ceiling) if objective_ratio_available else 0.0

    temps = _steady(series.get("temp_c", []))
    temp_c = max((v for _, v in temps), default=0.0)

    # Co-tenant presence over the whole run, not just the steady window:
    # a second process that left early still spent its memory and clock
    # cost on the window that was kept.
    process_counts = series.get("gpu_process_count", [])
    co_tenant = bool(process_counts) and max(v for _, v in process_counts) >= 2

    host_series = _steady(series.get("host_exposed_seconds_total", []))
    decode_series = _steady(series.get("request_decode_seconds", []))
    host_delta = _delta(host_series) if host_series else None
    decode_delta = _delta(decode_series) if decode_series else None
    host_ratio = (host_delta / decode_delta) if (host_delta is not None and decode_delta and decode_delta > 0) else 0.0
    host_available = bool(host_delta is not None and decode_delta and decode_delta > 0)

    facts: dict = {
        "power_ratio": power_ratio,
        "temp_c": temp_c,
        "decode_rate_tok_s": decode_rate,
        "decode_rate_method": rate_method,
        "decode_rate_available": rate_available,
        "reference_ceiling_tok_s": ceiling,
        "reference_ceiling_available": ceiling_available,
        "objective_ratio": objective_ratio,
        "objective_ratio_available": objective_ratio_available,
        "model_consistent": objective_ratio <= 1.0,
        "spec_tokens_per_forward": spec_factor,
        "spec_method": spec_method,
        "spec_acceptance_ratio": acceptance,
        "co_tenant": co_tenant,
        "host_exposed_ratio": host_ratio,
        "host_exposed_available": host_available,
        "steady_window": _span(power),
    }
    for key, points in series.items():
        if key.startswith("throttle."):
            facts[key] = any(v >= 0.5 for _, v in _steady(points))
    for fallback in THROTTLE_FALLBACKS:
        facts.setdefault(fallback, False)

    if request_rate_available:
        facts["engine_request_rate_tok_s"] = request_rate
        facts["engine_request_tokens_per_round"] = request_tpr if request_tpr_available else 0.0
        facts["engine_request_count"] = len(request_tokens)
        facts["engine_request_method"] = REQUEST_RATE_METHOD
    else:
        facts["engine_request_rate_tok_s"] = None
        facts["engine_request_tokens_per_round"] = None
        facts["engine_request_count"] = 0
        facts["engine_request_method"] = "no per-request series in this run"
    return facts


def references_from_run(run: Run, profile: dict) -> list[ReferenceModel]:
    if not run.workload.artifact_bytes:
        return []
    facts = facts_from_run(run, profile)
    return [
        dense_decode_reference(
            artifact_bytes=int(run.workload.artifact_bytes),
            bandwidth_gbps=float(profile.get("mem_bandwidth_spec_gbps", 1008.0)),
            spec_tokens_per_forward=facts["spec_tokens_per_forward"],
        )
    ]


def observations_from_run(run: Run) -> list[Observation]:
    """Measured summaries, one per metric name. Ids are metric names."""
    series = _by_metric(run)
    out: list[Observation] = []
    power = _steady(series.get("power_draw_w", []))
    if power:
        window = _span(power)
        vals = [v for _, v in power]
        limit = run.hardware.power_limit_w
        comparison = f"against the {limit} W limit" if limit else "against the configured power limit"
        out.append(Observation(run.id, "power_draw_mean_w", sum(vals) / len(vals), "W", window, comparison,
                               "mean over the steady window (first 10 percent dropped)", ["power_draw_w"]))
        out.append(Observation(run.id, "power_draw_max_w", max(vals), "W", window, comparison,
                               "max over the steady window (first 10 percent dropped)", ["power_draw_w"]))
    temps = _steady(series.get("temp_c", []))
    if temps:
        out.append(Observation(run.id, "temp_max_c", max(v for _, v in temps), "C", _span(temps),
                               "against the 83 C throttle point",
                               "max over the steady window (first 10 percent dropped)", ["temp_c"]))
    counts = series.get("gpu_process_count", [])
    if counts:
        out.append(Observation(run.id, "gpu_process_count", max(v for _, v in counts), "count",
                               _span(counts), "against 1, the engine alone",
                               "max over the window", ["gpu_process_count"]))
    host = _steady(series.get("host_exposed_seconds_total", []))
    decode = _steady(series.get("request_decode_seconds", []))
    if host and decode:
        hd = _delta(host)
        dd = _delta(decode)
        if hd is not None and dd and dd > 0:
            out.append(Observation(run.id, "host_exposed_ratio", hd / dd, "ratio",
                                   _span(host), "against 0.3, the host-bound threshold",
                                   "host exposed seconds / decode seconds",
                                   ["host_exposed_seconds_total"]))
    return out


def _placeholder(run: Run, rule: dict) -> Hypothesis:
    """An alternative that did not fire, ranked where the enum says it belongs."""
    return Hypothesis(
        id=f"h-{rule['id']}",
        run_id=run.id,
        claim=rule.get("claim", ""),
        mechanism=f"{rule.get('claim_kind', '')}: {rule.get('citation', '')}",
        rank_score=0.0,
        evidence=[],
        rules=[rule["id"]],
        alternatives=[],
        confidence=Quality.HYPOTHESIS,
    )


def hypotheses_from_run(run: Run, profile: dict, rules: list[dict]) -> list[Hypothesis]:
    """One hypothesis per fired rule, ranked, with its alternatives resolved.

    An alternative that also fired is carried as that hypothesis (without its
    own alternatives, so the nesting terminates). One that did not fire is a
    placeholder with ``Quality.HYPOTHESIS`` and a zero rank score, which is
    what that enum member is for.
    """
    facts = facts_from_run(run, profile)
    observation_ids = {o.metric for o in observations_from_run(run)}
    evidence_ids = observation_ids | set(EVIDENCE_FACTS)
    fired = [rule for rule in rules if fires(rule, facts)]
    known = {rule["id"]: rule for rule in rules}
    # A3 stopped the renderer from printing the fabricated rate; this keeps the
    # fabricated *ratio* out of the ranking. ``objective_ratio`` is the 0.0
    # sentinel when the run has no rate or no ceiling, and ``1.0 - 0.0`` is the
    # maximum headroom bonus a rule can be paid, for the worst-evidenced run.
    # A run that produced no ratio gets no headroom from it; a real ratio is
    # unchanged.
    headroom = (max(0.0, 1.0 - facts["objective_ratio"])
                if facts["objective_ratio_available"] else 0.0)

    hypotheses: dict[str, Hypothesis] = {}
    for rule in fired:
        confidence = rule_confidence(rule, facts)
        hypotheses[rule["id"]] = Hypothesis(
            id=f"h-{rule['id']}",
            run_id=run.id,
            claim=rule.get("claim", ""),
            mechanism=f"{rule.get('claim_kind', '')}: {rule.get('citation', '')}",
            rank_score=W_CONFIDENCE * confidence_weight(confidence) + W_HEADROOM * headroom,
            evidence=[m for m in rule.get("evidence_observations", []) if m in evidence_ids],
            rules=[rule["id"]],
            alternatives=[],
            confidence=confidence,
        )
    for rule in fired:
        alternatives: list[Hypothesis] = []
        for alternative_id in rule.get("alternatives", []):
            partner = hypotheses.get(alternative_id)
            if partner is not None:
                alternatives.append(replace(partner, alternatives=[]))
            elif alternative_id in known:
                alternatives.append(_placeholder(run, known[alternative_id]))
        hypotheses[rule["id"]].alternatives = alternatives
    return rank(list(hypotheses.values()))


def rank(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    return sorted(hypotheses, key=lambda h: (-h.rank_score, h.rules[0] if h.rules else h.id))
