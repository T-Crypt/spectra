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
    parser.error(f"unknown command: {args.command}")
    return 2
