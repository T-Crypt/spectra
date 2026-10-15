#!/usr/bin/env python3
"""Induced-bottleneck eval: the milestone's own success metric.

Three stages, each with its own precondition and its own recorded reason.

- E0, always runs: the counters recorded in docs/MILESTONE-1.md through
  ``facts_from_run``. No GPU, no server, no permission.
- E1 control: five repetitions of a fixed decode load with nothing changed.
  Needs the engine up, the card free of foreign compute, and room for the
  artifact. Also reports A6, the coefficient of variation of the speculative
  factor across the five.
- E2 treatment: E1's preconditions plus a writable power limit, applied and
  restored on every exit path, including an interrupt. The limit is set only
  when the value to restore was read first, a failed restore is printed loudly
  rather than swallowed, and a restore that raises is printed before it
  propagates. SIGINT and SIGTERM restore the limit before the process exits:
  the default SIGTERM action terminates without unwinding, so a ``finally``
  alone would leave the card capped. Never runs before E1 has run.

A stage that cannot run is skipped with its reason and is never a pass, per
docs/EVAL.md A8. The run's verdict goes to ``runs/<run_id>.eval.json`` and its
path is appended to ``Run.artifacts``; ``runs/`` is gitignored.

Run it from the repository root: ``python tests/eval_induced_bottleneck.py``.
"""

from __future__ import annotations

import contextlib
import json
import signal
import statistics
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adascope.analyze import facts_from_run, hypotheses_from_run  # noqa: E402
from adascope.engine import default_rules_path, load_rules  # noqa: E402
from adascope.observe import observe  # noqa: E402
from adascope.reference import load_profile  # noqa: E402
from adascope.store import load_run, save_run  # noqa: E402
from tests import load as load_driver  # noqa: E402
from tests.fixtures import machine  # noqa: E402
from tests.support import engine_available, engine_down_reason  # noqa: E402

REPETITIONS = 5
DURATION_S = 120.0
HZ = 2.0
SEEDED_RULE = "sm89.power-cap-limit"
TREATMENT_POWER_LIMIT_W = 250
A6_MAX_CV = 0.05
A4_MIN_HITS = 4
VRAM_MARGIN_BYTES = 2 * 1024**3
RUNS_DIR = Path("runs")
LABEL_WIDTH = 13


def _nvidia_smi(*args: str) -> str:
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True).stdout.strip()


def gpu_free_bytes() -> int | None:
    out = _nvidia_smi("--query-gpu=memory.free", "--format=csv,noheader,nounits")
    try:
        return int(float(out.splitlines()[0])) * 1024 * 1024
    except (IndexError, ValueError):
        return None


def compute_processes() -> list[str]:
    out = _nvidia_smi("--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader")
    return [line for line in out.splitlines() if line.strip()]


def power_limit_w() -> float | None:
    out = _nvidia_smi("--query-gpu=power.limit", "--format=csv,noheader,nounits")
    try:
        return float(out.splitlines()[0])
    except (IndexError, ValueError):
        return None


def set_power_limit(watts: int) -> tuple[bool, str]:
    """Try to write the power limit. Privileged, so it uses sudo -n."""
    result = subprocess.run(["sudo", "-n", "nvidia-smi", "-pl", str(watts)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    return True, result.stdout.strip()


class PowerLimitGuard:
    """The limit that must be put back, and the promise to put it back.

    E2 writes the power limit: the only code in this tree that changes a running
    system. The guard is armed *before* the write, because a write that raises
    or that is interrupted after it landed has still moved the limit, and it is
    disarmed only when the write reports that nothing was written. ``restore``
    puts the baseline back once and clears itself, so a signal handler that
    restores first cannot leave the unwinding ``finally`` a second restore to do
    -- and cannot restore a limit that was never changed.

    The writer is resolved at call time, not when the guard is built, so a test
    can replace :func:`set_power_limit` and drive this class without a GPU.
    """

    def __init__(self, set_limit=None) -> None:
        self._set_limit = set_limit
        self._watts: int | None = None

    @property
    def armed(self) -> bool:
        return self._watts is not None

    def arm(self, baseline_w: float) -> None:
        self._watts = int(baseline_w)

    def disarm(self) -> None:
        self._watts = None

    def restore(self) -> str:
        """Put the baseline back once. Returns a note, empty when it worked.

        A restore that itself raises -- ``subprocess.run(["sudo", ...])`` raises
        when sudo is not installed -- is printed before it propagates: at that
        moment the limit is still the treatment value and the operator has to be
        told which value to put back, not handed a bare traceback.
        """
        if self._watts is None:
            return ""
        watts, self._watts = self._watts, None
        writer = self._set_limit if self._set_limit is not None else set_power_limit
        try:
            restored, message = writer(watts)
        except BaseException as exc:
            note = (f"the power limit was NOT restored to {watts} W and may still be "
                    f"{TREATMENT_POWER_LIMIT_W} W: restoring it raised "
                    f"{type(exc).__name__}: {exc}; restore it by hand")
            _report_restore_failure(note)
            raise
        if not restored:
            note = (f"the power limit was NOT restored to {watts} W and may still be "
                    f"{TREATMENT_POWER_LIMIT_W} W: {message}; restore it by hand")
            _report_restore_failure(note)
            return note
        return ""


def _report_restore_failure(note: str) -> None:
    print(f"E2 restore failed: {note}", file=sys.stderr, flush=True)


# The guard a signal handler restores from. Only ever armed from run_stage.
_ACTIVE_GUARD: PowerLimitGuard | None = None


def _restore_and_exit(signum: int, frame) -> None:
    """SIGINT or SIGTERM while the limit may be changed: restore, then exit.

    A ``finally`` cannot cover this. The default action for SIGTERM terminates
    the process without unwinding, so the restore never runs and the card stays
    capped for the rest of the session; E2 is ten or more minutes of
    repetitions, so that window is wide. The guard restores once, so the
    unwinding that follows the ``sys.exit`` below finds nothing left to do.
    """
    guard = _ACTIVE_GUARD
    if guard is not None:
        try:
            guard.restore()
        except BaseException as exc:
            # The guard has already printed the value to put back; this line adds
            # the signal that interrupted the run, then the process still exits.
            print(f"E2 signal handler: restoring after signal {signum} raised "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    sys.exit(128 + signum)


@contextlib.contextmanager
def restore_on_signal(guard: PowerLimitGuard):
    """Install the restore-on-signal handlers while the limit may change."""
    global _ACTIVE_GUARD
    handled = (signal.SIGINT, signal.SIGTERM)
    previous = {signum: signal.getsignal(signum) for signum in handled}
    _ACTIVE_GUARD = guard
    try:
        for signum in handled:
            try:
                signal.signal(signum, _restore_and_exit)
            except ValueError:
                # Signals are only handled in the main thread. Anywhere else
                # there is nothing to install, and the caller's finally stays
                # the only restore path -- which is what a thread that changes
                # the power limit gets.
                pass
        yield guard
    finally:
        _ACTIVE_GUARD = None
        for signum, handler in previous.items():
            try:
                signal.signal(signum, handler)
            except ValueError:
                pass


def preflight(artifact_bytes: int | None) -> tuple[bool, str]:
    """E1 and E2 preconditions, re-checked at run time.

    The engine holds the card once it is loaded, so "the card is free" means
    free of a *foreign* compute process: more than one compute process on a
    single-engine machine means a co-tenant, and a contended run is recorded as
    inconclusive rather than measured.
    """
    processes = compute_processes()
    if len(processes) > 1:
        return False, "contended card: " + "; ".join(processes)
    if not engine_available(machine.ENGINE_HOST, machine.ENGINE_PORT):
        return False, engine_down_reason(machine.ENGINE_HOST, machine.ENGINE_PORT)
    free = gpu_free_bytes()
    if free is None:
        return False, "nvidia-smi did not report free VRAM"
    if not processes and artifact_bytes and free < artifact_bytes + VRAM_MARGIN_BYTES:
        return False, (f"the artifact needs {artifact_bytes} bytes plus a margin and only "
                       f"{free} bytes are free")
    return True, ""


def _model_id() -> str:
    from adascope.adapters.lmcompat import LmCompat

    models = LmCompat(machine.ENGINE_HOST, machine.ENGINE_PORT).models()
    return str(models[0].get("id", "")) if models else ""


def _counter_moved(run) -> bool:
    for series in run.series:
        if series.metric == "tokens_predicted_total" and len(series.samples) >= 2:
            return series.samples[-1][1] - series.samples[0][1] > 0
    return False


def _verdict(stage: str, run, facts: dict, rules: list[dict]) -> dict:
    """One repetition's verdict, per docs/EVAL.md (d) and its inconclusive list."""
    ranked = hypotheses_from_run(run, load_profile(), rules)
    top = ranked[0].rules[0] if ranked and ranked[0].rules else None
    if len(ranked) >= 2 and ranked[0].rank_score == ranked[1].rank_score:
        return {"top_rule_id": top, "verdict": "inconclusive",
                "reason": "two rules tie for first rank: "
                          + ", ".join(h.rules[0] for h in ranked[:2] if h.rules)}
    if stage == "E1":
        if top == SEEDED_RULE:
            return {"top_rule_id": top, "verdict": "rejected",
                    "reason": f"the seeded rule {SEEDED_RULE} ranks first in the control, "
                              "where the cause was not induced"}
        return {"top_rule_id": top, "verdict": "confirmed",
                "reason": f"no rule fired" if top is None else f"{top} ranks first in the control"}
    if top != SEEDED_RULE:
        return {"top_rule_id": top, "verdict": "rejected",
                "reason": f"the top-ranked rule is {top}, not {SEEDED_RULE}"}
    if not facts["throttle.sw_power_cap"]:
        return {"top_rule_id": top, "verdict": "inconclusive",
                "reason": "A5 failed: throttle.sw_power_cap is false in the steady window"}
    return {"top_rule_id": top, "verdict": "confirmed",
            "reason": "throttle.sw_power_cap true in the steady window"}


def run_repetition(stage: str, index: int, artifact_path: str, model_id: str,
                   rules: list[dict], variable: dict) -> dict:
    """Observe one repetition under load, analyse it, and record the verdict."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    thread = threading.Thread(target=load_driver.drive_decode,
                              args=(machine.ENGINE_HOST, machine.ENGINE_PORT, model_id, stop),
                              daemon=True)
    thread.start()
    try:
        path = observe(f"{machine.ENGINE_HOST}:{machine.ENGINE_PORT}", duration_s=DURATION_S, hz=HZ,
                       artifact_path=artifact_path, out=RUNS_DIR)
    finally:
        stop.set()
        thread.join(timeout=5.0)
    run = load_run(path)
    facts = facts_from_run(run, load_profile())

    if not _counter_moved(run):
        verdict = {"top_rule_id": None, "verdict": "inconclusive", "reason": "no decode observed"}
    else:
        verdict = _verdict(stage, run, facts, rules)

    record = {
        "stage": stage,
        "repetition": index,
        "seeded_cause": SEEDED_RULE,
        "variable": variable,
        "top_rule_id": verdict["top_rule_id"],
        "verdict": verdict["verdict"],
        "reason": verdict["reason"],
        "decode_rate_tok_s": facts["decode_rate_tok_s"],
        "spec_tokens_per_forward": facts["spec_tokens_per_forward"],
        "objective_ratio": facts["objective_ratio"],
    }
    eval_path = RUNS_DIR / f"{run.id}.eval.json"
    eval_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    run.artifacts = list(run.artifacts) + [str(eval_path)]
    save_run(run, RUNS_DIR)
    return record


def run_stage(stage: str, artifact_path: str, rules: list[dict]) -> tuple[str, str]:
    """Five repetitions of one stage. Returns (verdict, note).

    E2 writes the power limit, the only action in this tree that changes a
    running system, so it changes the limit only when it has read the value it
    must put back, and every exit path restores it: the normal one, an
    exception, an interrupt, and SIGINT or SIGTERM, which do not unwind by
    themselves and are covered by ``restore_on_signal``. A restore that fails,
    or that raises, says so on stderr naming the value to put back by hand; the
    note also reaches the caller's verdict. A test must never leave the card in
    a state it did not restore.
    """
    model_id = _model_id()
    baseline = power_limit_w()
    variable = {"name": "power_limit_w", "baseline": baseline, "treatment": None}
    guard = PowerLimitGuard()
    if stage == "E2" and baseline is None:
        return "inconclusive", ("nvidia-smi did not report the power limit, so a change could not "
                                "be restored: refusing to set it")

    with restore_on_signal(guard):
        restore_note = ""
        try:
            if stage == "E2":
                # Armed before the write: a write that raises, or that is
                # interrupted after it landed, has still moved the limit.
                guard.arm(baseline)
                ok, message = set_power_limit(TREATMENT_POWER_LIMIT_W)
                if not ok:
                    guard.disarm()
                    return "inconclusive", f"the power limit is not writable: {message}"
                variable["treatment"] = TREATMENT_POWER_LIMIT_W
            records = [run_repetition(stage, i, artifact_path, model_id, rules, variable)
                       for i in range(1, REPETITIONS + 1)]
        finally:
            restore_note = guard.restore()

    verdicts = [r["verdict"] for r in records]
    if stage == "E1":
        factors = [r["spec_tokens_per_forward"] for r in records]
        cv = (statistics.stdev(factors) / statistics.fmean(factors)) if len(factors) > 1 and statistics.fmean(factors) else 0.0
        hits = sum(1 for r in records if r["top_rule_id"] == SEEDED_RULE)
        if cv > A6_MAX_CV:
            verdict, note = "inconclusive", f"spec factor CV above 5 percent: {cv:.3f}"
        elif hits == 0:
            verdict, note = "confirmed", f"0 of {REPETITIONS} control runs ranked {SEEDED_RULE} first"
        else:
            verdict, note = "rejected", f"{hits} of {REPETITIONS} control runs ranked {SEEDED_RULE} first"
    else:
        confirmed = verdicts.count("confirmed")
        if confirmed >= A4_MIN_HITS:
            verdict, note = "confirmed", f"{confirmed} of {REPETITIONS} treatment runs ranked {SEEDED_RULE} first"
        elif verdicts.count("inconclusive") == REPETITIONS:
            verdict, note = "inconclusive", "no usable treatment repetition"
        else:
            verdict, note = "rejected", f"{confirmed} of {REPETITIONS} treatment runs ranked {SEEDED_RULE} first"
    if restore_note:
        note = f"{note}; {restore_note}"
    return verdict, note


def run_e0() -> tuple[str, str]:
    """The recorded counters, asserted. No GPU, no server, no permission."""
    from tests.fixtures.recorded_run import recorded_run

    facts = facts_from_run(recorded_run(), load_profile())
    numbers = (f"rate {facts['decode_rate_tok_s']:.4f} tok/s, "
               f"factor {facts['spec_tokens_per_forward']:.4f}, "
               f"ceiling {facts['reference_ceiling_tok_s']:.4f}, "
               f"ratio {facts['objective_ratio']:.4f}")
    try:
        assert abs(facts["decode_rate_tok_s"] - 109.0954) <= 0.01
        assert abs(facts["spec_tokens_per_forward"] - 3.0195) <= 0.03
        assert abs(facts["reference_ceiling_tok_s"] - 167.1348) <= 1.0
        assert abs(facts["objective_ratio"] - 0.6527) <= 0.003
        assert facts["model_consistent"] is True
    except AssertionError:
        return "rejected", f"E0 recorded counters: {numbers}  mismatch"
    return "confirmed", f"E0 recorded counters: {numbers}  ok"


def main() -> int:
    rules = load_rules(default_rules_path())
    artifact_path = machine.LIVE_ARTIFACT_PATH
    artifact_bytes = machine.artifact_bytes(artifact_path)

    stage_lines: list[tuple[str, str, str]] = []
    e0_verdict, e0_line = run_e0()
    print(e0_line, flush=True)
    stage_lines.append(("E0", e0_verdict, e0_line))


    ok, reason = preflight(artifact_bytes)
    if ok:
        e1_verdict, e1_note = run_stage("E1", artifact_path, rules)
        print(f"{'E1 control:':<{LABEL_WIDTH}} {e1_verdict} - {e1_note}", flush=True)
    else:
        e1_verdict, e1_note = "skipped", reason
        print(f"{'E1 control:':<{LABEL_WIDTH}} skipped - {reason}", flush=True)
    stage_lines.append(("E1", e1_verdict, e1_note))

    if e1_verdict == "skipped":
        e2_verdict, e2_note = "skipped", e1_note
        print(f"{'E2 treatment:':<{LABEL_WIDTH}} skipped - {e1_note}", flush=True)
    else:
        e2_verdict, e2_note = run_stage("E2", artifact_path, rules)
        print(f"{'E2 treatment:':<{LABEL_WIDTH}} {e2_verdict} - {e2_note}", flush=True)
    stage_lines.append(("E2", e2_verdict, e2_note))

    # The summary counts the two live stages: A4 is a claim about E1 and E2.
    live = [verdict for stage, verdict, _ in stage_lines if stage != "E0"]
    print(f"summary: {live.count('confirmed')} confirmed, {live.count('rejected')} rejected, "
          f"{live.count('skipped')} skipped, {live.count('inconclusive')} inconclusive "
          f"(A4 requires 5+5 live repetitions)", flush=True)
    any_rejected = any(verdict == "rejected" for _, verdict, _ in stage_lines)
    return 1 if any_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
