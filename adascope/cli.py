"""Command line entry point.

Phase 1 builds up the subcommands one commit at a time. This file is the thin
shell. It validates arguments at the boundary and hands work to the modules.
A failed command returns a non-zero status.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    from .adapters.engines import ENGINE_IDS

    parser = argparse.ArgumentParser(
        prog="spectra",
        description="Architecture-aware GPU performance diagnosis.",
    )
    subs = parser.add_subparsers(dest="command")

    obs = subs.add_parser("observe", help="Sample live adapters and store a Run.")
    obs.add_argument("--target", required=True, help="Engine host and port as HOST:PORT.")
    obs.add_argument("--duration", type=float, default=30.0)
    obs.add_argument("--hz", type=float, default=2.0)
    obs.add_argument("--artifact", default="")
    obs.add_argument("--config", default=None, help="JSON file holding launch config.")
    obs.add_argument("--metrics-jsonl", default=None)
    obs.add_argument("--out", default="runs")
    obs.add_argument("--engine", default="auto",
                     help="Engine name table: auto (detected from /metrics) or one of "
                          + ", ".join(ENGINE_IDS))

    ben = subs.add_parser("bench", help="Drive a workload, sample adapters, and store a Run.")
    ben.add_argument("--target", required=True, help="Engine host and port as HOST:PORT.")
    ben.add_argument("--duration", type=float, default=60.0)
    ben.add_argument("--hz", type=float, default=2.0)
    ben.add_argument("--prompt-words", type=int, default=256,
                     help="Prompt length in words (default 256).")
    ben.add_argument("--completion-tokens", type=int, default=256,
                     help="Token ceiling per completion (default 256).")
    ben.add_argument("--concurrency", type=int, default=1,
                     help="Completions in flight (default 1).")
    ben.add_argument("--artifact", default="")
    ben.add_argument("--config", default=None, help="JSON file holding launch config.")
    ben.add_argument("--metrics-jsonl", default=None)
    ben.add_argument("--out", default="runs")
    ben.add_argument("--engine", default="auto",
                     help="Engine name table: auto (detected from /metrics) or one of "
                          + ", ".join(ENGINE_IDS))

    rep = subs.add_parser("report", help="Render a stored Run as text.")
    rep.add_argument("path", help="Path to a stored run JSON file.")
    rep.add_argument("--profile", default=None)
    rep.add_argument("--rules", default=None)

    cmp_p = subs.add_parser("compare", help="Compare two stored runs.")
    cmp_p.add_argument("run_a", help="Path to first run JSON.")
    cmp_p.add_argument("run_b", help="Path to second run JSON.")
    cmp_p.add_argument("--profile", default=None)

    runs_p = subs.add_parser("runs", help="List stored runs.")
    runs_p.add_argument("--root", default="runs")

    findings_p = subs.add_parser("findings", help="List or query stored findings.")
    findings_p.add_argument("--root", default="findings")
    findings_p.add_argument("--arch", default=None)
    findings_p.add_argument("--engine", default=None)
    findings_p.add_argument("--workload-class", default=None)
    findings_p.add_argument("--variable", default=None)
    findings_p.add_argument("--direction", default=None)
    findings_p.add_argument("--verdict", default=None)

    exp = subs.add_parser("experiment", help="Plan or evaluate an experiment.")
    exp_sub = exp.add_subparsers(dest="experiment_command")
    plan_p = exp_sub.add_parser("plan", help="Plan an experiment from a baseline run.")
    plan_p.add_argument("--baseline", required=True)
    plan_p.add_argument("--hypothesis", required=True)
    plan_p.add_argument("--variable", required=True)
    plan_p.add_argument("--treatment", required=True)
    plan_p.add_argument("--out", default="experiments")
    plan_p.add_argument("--threshold", type=float, default=0.05)
    eval_p = exp_sub.add_parser("evaluate", help="Evaluate baseline vs treatment into a finding.")
    eval_p.add_argument("--baseline", required=True)
    eval_p.add_argument("--treatment", required=True)
    eval_p.add_argument("--experiment", required=True)
    eval_p.add_argument("--out", default="findings")
    eval_p.add_argument("--experiments-root", default="experiments")
    show_p = exp_sub.add_parser("show", help="Show an experiment runbook.")
    show_p.add_argument("id")
    show_p.add_argument("--root", default="experiments")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "observe":
        from .observe import observe, parse_target

        try:
            parse_target(args.target)
            path = observe(
                args.target,
                duration_s=args.duration,
                hz=args.hz,
                artifact_path=args.artifact,
                config_file=args.config,
                jsonl_path=args.metrics_jsonl,
                out=args.out,
                engine=args.engine,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"observe: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0
    if args.command == "bench":
        from .observe import observe, parse_target

        try:
            parse_target(args.target)
            path = observe(
                args.target,
                duration_s=args.duration,
                hz=args.hz,
                artifact_path=args.artifact,
                config_file=args.config,
                jsonl_path=args.metrics_jsonl,
                out=args.out,
                engine=args.engine,
                load={"prompt_words": args.prompt_words,
                      "completion_tokens": args.completion_tokens,
                      "concurrency": args.concurrency},
            )
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"bench: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0
    if args.command == "report":
        from .engine import default_rules_path, load_rules
        from .reference import default_profile_path, load_profile
        from .report import render
        from .store import load_run

        try:
            run = load_run(args.path)
            profile = load_profile(args.profile or default_profile_path())
            rendered = render(run, profile, load_rules(args.rules or default_rules_path()))
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"report: {exc}", file=sys.stderr)
            return 2
        print(rendered, end="")
        return 0
    if args.command == "compare":
        from .fingerprint import compare_runs
        from .reference import default_profile_path, load_profile
        from .store import load_run

        try:
            run_a = load_run(args.run_a)
            run_b = load_run(args.run_b)
            profile = load_profile(args.profile or default_profile_path())
            result = compare_runs(run_a, run_b, profile)
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"compare: {exc}", file=sys.stderr)
            return 2
        import json
        print(json.dumps({
            "verdict": result.verdict.value,
            "reason": result.reason,
            "differences": result.differences,
            "config_diff": result.config_diff,
            "metric_deltas": result.metric_deltas,
        }, indent=2))
        return 0
    if args.command == "runs":
        from .store import list_runs

        try:
            for path in list_runs(args.root):
                print(path)
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"runs: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "findings":
        from .store import query_findings

        try:
            findings = query_findings(
                args.root,
                arch=args.arch,
                engine_id=args.engine,
                workload_class=args.workload_class,
                variable=args.variable,
                direction=args.direction,
                verdict=args.verdict,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"findings: {exc}", file=sys.stderr)
            return 2
        import json
        for finding in findings:
            print(json.dumps({
                "id": finding.id,
                "verdict": finding.verdict.value,
                "hypothesis_id": finding.hypothesis_id,
                "experiment_id": finding.experiment_id,
                "delta": finding.delta,
                "variable": finding.variable,
                "direction": finding.direction,
            }))
        return 0
    if args.command == "experiment":
        from .experiment import (
            approve,
            evaluate_experiment,
            plan_experiment,
            render_runbook,
        )
        from .reference import default_profile_path, load_profile
        from .store import (
            load_experiment,
            load_run,
            save_experiment,
            save_finding,
        )

        sub = getattr(args, "experiment_command", None)
        if sub == "plan":
            try:
                baseline = load_run(args.baseline)
                exp = plan_experiment(
                    args.hypothesis,
                    baseline,
                    args.variable,
                    _coerce(args.treatment),
                    experiment_id=None,
                )
                exp.success_criteria["threshold"] = args.threshold
                path = save_experiment(exp, args.out)
            except (ValueError, OSError, RuntimeError) as exc:
                print(f"experiment: {exc}", file=sys.stderr)
                return 2
            print(path)
            print(render_runbook(exp))
            return 0
        if sub == "evaluate":
            try:
                baseline = load_run(args.baseline)
                treatment = load_run(args.treatment)
                experiment = load_experiment(
                    _find_experiment(args.experiments_root, args.experiment))
                profile = load_profile(default_profile_path())
                finding = evaluate_experiment(experiment, baseline, treatment, profile)
                finish = experiment
                from .model import ExperimentStatus
                finish.status = ExperimentStatus.DONE
                finish.treatment_run_id = treatment.id
                save_experiment(finish, args.experiments_root)
                path = save_finding(finding, args.out)
            except (ValueError, OSError, RuntimeError) as exc:
                print(f"experiment: {exc}", file=sys.stderr)
                return 2
            print(path)
            return 0
        if sub == "show":
            try:
                experiment = load_experiment(
                    _find_experiment(args.root, args.id))
            except (ValueError, OSError, RuntimeError) as exc:
                print(f"experiment: {exc}", file=sys.stderr)
                return 2
            print(render_runbook(experiment))
            return 0
        parser.error("experiment requires a subcommand")
        return 2
    return 0


def _coerce(value: str):
    """Coerce a CLI string into int/float/bool/str for experiment values."""
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _find_experiment(root: str, experiment_id: str) -> str:
    from pathlib import Path

    name = experiment_id
    if name.endswith(".experiment"):
        name = name[: -len(".experiment")]
    candidate = Path(root) / f"{name}.experiment.json"
    if candidate.is_file():
        return str(candidate)
    # Fall back to a direct path.
    if Path(experiment_id).is_file():
        return experiment_id
    # Maybe the caller passed the full file name.
    if Path(root, experiment_id).is_file():
        return str(Path(root, experiment_id))
    raise FileNotFoundError(f"experiment {experiment_id!r} not found under {root}")
