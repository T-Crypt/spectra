"""Experiment engine: plan, diff, runbook, evaluate, rollback.

Spectra never applies a configuration change. It plans an experiment,
renders the diff and a runbook, and evaluates two stored runs once a human
has run them. Rollback is the stored baseline value, never a guess.
"""

from __future__ import annotations

from .model import (
    Experiment,
    ExperimentStatus,
    Finding,
    FindingVerdict,
    Run,
)


def plan_experiment(
    hypothesis_id: str,
    baseline_run: Run,
    variable: str,
    treatment_value,
    experiment_id: str | None = None,
    success_criteria: dict | None = None,
    notes: str = "",
) -> Experiment:
    """Plan a single-variable experiment against a baseline run."""
    if not isinstance(variable, str) or not variable:
        raise ValueError("variable must be a non-empty config key")
    baseline_config = baseline_run.workload.config if isinstance(baseline_run.workload.config, dict) else {}
    if variable not in baseline_config:
        raise ValueError(f"variable {variable!r} is not present in the baseline config")
    baseline_value = baseline_config[variable]
    if baseline_value == treatment_value:
        raise ValueError("treatment value must differ from the baseline value")
    criteria = dict(success_criteria or {})
    criteria.setdefault("metric", "decode_rate_tok_s")
    criteria.setdefault("direction", "maximize")
    criteria.setdefault("threshold", 0.05)
    eid = experiment_id or f"exp-{baseline_run.id}-{variable}"
    return Experiment(
        id=eid,
        hypothesis_id=hypothesis_id,
        baseline_run_id=baseline_run.id,
        variable=variable,
        baseline_value=baseline_value,
        treatment_value=treatment_value,
        success_criteria=criteria,
        rollback={"variable": variable, "value": baseline_value},
        status=ExperimentStatus.PLANNED,
        notes=notes,
    )


def config_diff_text(baseline_config: dict, treatment_config: dict) -> str:
    """Render a config diff as text. Pure."""
    diffs = _config_diff_simple(baseline_config, treatment_config)
    if not diffs:
        return "no config differences"
    lines = []
    for d in diffs:
        lines.append(f"  {d['key']}: {d['a']!r} -> {d['b']!r}")
    return "\n".join(lines)


def _config_diff_simple(a: dict, b: dict) -> list[dict]:
    a = a if isinstance(a, dict) else {}
    b = b if isinstance(b, dict) else {}
    out = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            out.append({"key": key, "a": a.get(key), "b": b.get(key)})
    return out


def render_runbook(experiment: Experiment) -> str:
    """Render a runbook for a human to execute."""
    lines = [
        f"Experiment: {experiment.id}",
        f"Hypothesis: {experiment.hypothesis_id}",
        f"Baseline run: {experiment.baseline_run_id}",
        f"Variable: {experiment.variable}",
        f"  baseline: {experiment.baseline_value!r}",
        f"  treatment: {experiment.treatment_value!r}",
        "",
        "Steps:",
        "1. Record the baseline run id above (already stored).",
        f"2. Change {experiment.variable} from {experiment.baseline_value!r} to "
        f"{experiment.treatment_value!r} in the engine launch config.",
        "3. Relaunch the engine with the new config.",
        "4. Run: spectra bench --target HOST:PORT --duration ... --out runs/<treatment>.json",
        "5. Run: spectra experiment evaluate --baseline <baseline> --treatment <treatment> "
        f"--experiment {experiment.id}",
        "6. Restore the baseline config (rollback below) and relaunch.",
        "",
        "Rollback:",
        f"  set {experiment.rollback.get('variable')} back to "
        f"{experiment.rollback.get('value')!r}",
        "",
        "Success criteria:",
        f"  {experiment.success_criteria.get('metric')} "
        f"{experiment.success_criteria.get('direction')} by "
        f"{experiment.success_criteria.get('threshold')}",
    ]
    return "\n".join(lines) + "\n"


def treatment_config(baseline_run: Run, experiment: Experiment) -> dict:
    """The config an experiment's treatment run should carry."""
    base = baseline_run.workload.config if isinstance(baseline_run.workload.config, dict) else {}
    out = dict(base)
    out[experiment.variable] = experiment.treatment_value
    return out


def evaluate_experiment(
    experiment: Experiment,
    baseline_run: Run,
    treatment_run: Run,
    profile: dict,
    finding_id: str | None = None,
) -> Finding:
    """Evaluate two stored runs into a Finding. Pure."""
    from .analyze import facts_from_run

    fb = facts_from_run(baseline_run, profile)
    ft = facts_from_run(treatment_run, profile)
    metric = experiment.success_criteria.get("metric", "decode_rate_tok_s")
    direction = experiment.success_criteria.get("direction", "maximize")
    threshold = float(experiment.success_criteria.get("threshold", 0.05))

    base_val = fb.get(metric)
    treat_val = ft.get(metric)
    # Base and treatment must both be real numbers.
    if not isinstance(base_val, (int, float)) or not isinstance(treat_val, (int, float)):
        return Finding(
            id=finding_id or f"finding-{experiment.id}",
            hypothesis_id=experiment.hypothesis_id,
            experiment_id=experiment.id,
            verdict=FindingVerdict.INCONCLUSIVE,
            delta={"metric": metric, "baseline": base_val, "treatment": treat_val,
                   "unit": "", "n_runs": 1, "spread": 0.0},
            notes="metric unavailable in one of the runs",
            artifacts=[baseline_run.id, treatment_run.id],
            arch=baseline_run.hardware.arch,
            engine_id=baseline_run.workload.engine_id,
            workload_class="dense-decode",
            variable=experiment.variable,
            direction=experiment.success_criteria.get("direction"),
        )

    delta = treat_val - base_val
    if base_val not in (0, 0.0):
        relative = delta / base_val
    else:
        relative = 0.0

    if direction == "maximize":
        success = relative >= threshold
    else:
        success = relative <= -threshold

    # Spread: single repetition, so zero. Multiple reps would aggregate.
    if success:
        verdict = FindingVerdict.CONFIRMED
    elif abs(relative) < threshold:
        verdict = FindingVerdict.INCONCLUSIVE
    else:
        verdict = FindingVerdict.REJECTED

    # Negative result handling: a rejected finding is still a finding.
    return Finding(
        id=finding_id or f"finding-{experiment.id}",
        hypothesis_id=experiment.hypothesis_id,
        experiment_id=experiment.id,
        verdict=verdict,
        delta={
            "metric": metric,
            "baseline": base_val,
            "treatment": treat_val,
            "unit": "tok/s" if metric.endswith("tok_s") else "",
            "delta": delta,
            "relative": relative,
            "n_runs": 1,
            "spread": 0.0,
        },
        notes=f"relative change {relative:+.3f} against threshold {threshold:+.3f}",
        artifacts=[baseline_run.id, treatment_run.id],
        arch=baseline_run.hardware.arch,
        engine_id=baseline_run.workload.engine_id,
        workload_class="dense-decode",
        variable=experiment.variable,
        direction=experiment.success_criteria.get("direction"),
    )


def approve(experiment: Experiment) -> Experiment:
    experiment.status = ExperimentStatus.APPROVED
    return experiment


def start(experiment: Experiment) -> Experiment:
    experiment.status = ExperimentStatus.RUNNING
    return experiment


def finish(experiment: Experiment, treatment_run_id: str) -> Experiment:
    experiment.status = ExperimentStatus.DONE
    experiment.treatment_run_id = treatment_run_id
    return experiment


def abort(experiment: Experiment, reason: str = "") -> Experiment:
    experiment.status = ExperimentStatus.ABORTED
    experiment.notes = (experiment.notes + " " + reason).strip()
    return experiment

    # Keep _config_diff importable name for callers.
    return experiment
