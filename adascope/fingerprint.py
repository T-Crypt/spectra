"""Workload fingerprints and differential comparison of two runs.

A fingerprint is the identity of a run's workload, hardware and environment,
stripped of its measurements. Two runs with the same fingerprint are
reproducible repeats; two with different fingerprints are different
experiments, and the difference is the material change.

Comparison never mutates either run. It returns a structured verdict plus
the list of material differences so a reader can reject the comparison by
rejecting a field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .analyze import facts_from_run
from .model import (
    Comparison,
    ComparisonVerdict,
    Fingerprint,
    Run,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fingerprint(run: Run) -> Fingerprint:
    """Derive a fingerprint from a stored run. Pure."""
    hw = run.hardware
    wl = run.workload
    env = run.environment if isinstance(run.environment, dict) else {}
    procs = env.get("gpu_processes") or []
    contention = len(procs) >= 2
    metrics = sorted({s.metric for s in run.series})
    return Fingerprint(
        run_id=run.id,
        arch=hw.arch,
        engine_id=wl.engine_id,
        engine_version=wl.engine_version,
        model_id=wl.model_id,
        artifact_bytes=wl.artifact_bytes,
        artifact_sha256=wl.artifact_sha256,
        objective=dict(wl.objective) if isinstance(wl.objective, dict) else {},
        config=dict(wl.config) if isinstance(wl.config, dict) else {},
        hardware_name=hw.name,
        driver_version=hw.driver_version,
        cuda_driver_version=hw.cuda_driver_version,
        contention=contention,
        sources=list(run.sources),
        metrics=metrics,
        sampling=dict(run.sampling) if isinstance(run.sampling, dict) else {},
        created_at=run.started_at or _utc_now(),
    )


def fingerprint_id(fp: Fingerprint) -> str:
    """A stable id for a fingerprint, from its canonical JSON."""
    payload = json.dumps(fp_to_dict(fp), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fp_to_dict(fp: Fingerprint) -> dict:
    from .model import to_dict

    return to_dict(fp)


def _hardware_differences(run_a: Run, run_b: Run) -> list[dict]:
    diffs: list[dict] = []
    fields = [
        ("name", "hardware_name"),
        ("compute_capability", "compute_capability"),
        ("vram_total_bytes", "vram_total_bytes"),
        ("power_limit_w", "power_limit_w"),
        ("power_default_w", "power_default_w"),
        ("power_max_w", "power_max_w"),
        ("clock_sm_max_mhz", "clock_sm_max_mhz"),
        ("clock_mem_max_mhz", "clock_mem_max_mhz"),
        ("driver_version", "driver_version"),
        ("cuda_driver_version", "cuda_driver_version"),
        ("mem_bandwidth_spec_gbps", "mem_bandwidth_spec_gbps"),
    ]
    for attr, label in fields:
        a = getattr(run_a.hardware, attr, None)
        b = getattr(run_b.hardware, attr, None)
        if a != b:
            diffs.append({"field": f"hardware.{label}", "a": a, "b": b})
    return diffs


def _config_diff(run_a: Run, run_b: Run) -> list[dict]:
    ca = run_a.workload.config if isinstance(run_a.workload.config, dict) else {}
    cb = run_b.workload.config if isinstance(run_b.workload.config, dict) else {}
    out: list[dict] = []
    for key in sorted(set(ca) | set(cb)):
        if ca.get(key) != cb.get(key):
            out.append({"key": key, "a": ca.get(key), "b": cb.get(key)})
    return out


def compare_runs(run_a: Run, run_b: Run, profile: dict) -> Comparison:
    """Compare two runs and return a structured verdict."""
    fa = fingerprint(run_a)
    fb = fingerprint(run_b)
    differences: list[dict] = []

    # Identity fields that must match for a comparison to be meaningful.
    if fa.arch != fb.arch:
        differences.append({"field": "arch", "a": fa.arch, "b": fb.arch})
    if fa.engine_id != fb.engine_id:
        differences.append({"field": "engine_id", "a": fa.engine_id, "b": fb.engine_id})
    if fa.model_id != fb.model_id or fa.artifact_bytes != fb.artifact_bytes:
        differences.append({"field": "model", "a": fa.model_id, "b": fb.model_id})
    if fa.objective.get("metric") != fb.objective.get("metric"):
        differences.append({"field": "objective.metric",
                            "a": fa.objective.get("metric"), "b": fb.objective.get("metric")})

    hw_diffs = _hardware_differences(run_a, run_b)
    differences.extend(hw_diffs)

    if fa.contention != fb.contention:
        differences.append({"field": "contention", "a": fa.contention, "b": fb.contention})

    if fa.sources != fb.sources:
        differences.append({"field": "sources", "a": fa.sources, "b": fb.sources})

    cfg_diff = _config_diff(run_a, run_b)

    # Metric deltas from derived facts.
    facts_a = facts_from_run(run_a, profile)
    facts_b = facts_from_run(run_b, profile)
    metric_deltas: dict = {}
    for key in ("decode_rate_tok_s", "objective_ratio", "power_ratio",
                "spec_tokens_per_forward", "spec_acceptance_ratio"):
        a = facts_a.get(key)
        b = facts_b.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            delta = b - a
            pct = (delta / a * 100.0) if a not in (0, 0.0) else None
            metric_deltas[key] = {"a": a, "b": b, "delta": delta, "pct": pct}

    # Verdict.
    identity_broken = any(d["field"] in ("arch", "engine_id", "model", "objective.metric")
                          for d in differences)
    if identity_broken:
        verdict = ComparisonVerdict.NOT_COMPARABLE
        reason = "identity differs: " + ", ".join(
            d["field"] for d in differences
            if d["field"] in ("arch", "engine_id", "model", "objective.metric"))
    elif hw_diffs or fa.contention != fb.contention:
        verdict = ComparisonVerdict.COMPARABLE_WITH_NORMALIZATION
        reason = "hardware or contention differs; normalize before comparing rates"
    else:
        verdict = ComparisonVerdict.COMPARABLE
        reason = "same identity, hardware and contention"

    return Comparison(
        run_a_id=run_a.id,
        run_b_id=run_b.id,
        verdict=verdict,
        reason=reason,
        differences=differences,
        config_diff=cfg_diff,
        metric_deltas=metric_deltas,
    )
