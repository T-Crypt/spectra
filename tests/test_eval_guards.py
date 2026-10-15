"""Guards on the eval's one privileged action.

E2 sets the GPU power limit, the only code in this tree that changes a running
system. These tests pin every way that could leave the card changed: setting a
limit whose old value could not be read back, failing to restore the old value
without saying so, a restore that raises instead of returning, a write that
raises after it landed, and the signals that must not leave the card capped --
SIGTERM, which terminates without unwinding, and SIGINT.

``run_stage`` is called with the power-limit functions, the model lookup and the
repetitions faked, so no limit is read or written and no GPU is touched here.
The signal test runs a real subprocess and sends it a real SIGTERM; its writer
is the same fake, so it writes an integer to a file and nothing to the card.
"""

import contextlib
import io
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests import eval_induced_bottleneck as ev

# Driven in a child process: the guard, the writer and the repetitions are
# replaced before run_stage is called, so the real nvidia-smi is never invoked.
# The child records every write and then sleeps inside a repetition, which is
# the window a SIGTERM would otherwise leave the card capped in.
CHILD = '''
import sys, time
sys.path.insert(0, {root!r})
from tests import eval_induced_bottleneck as ev

log = open({log!r}, "a")

def fake_set_power_limit(watts):
    log.write(str(int(watts)) + "\\n")
    log.flush()
    return True, "fake nvidia-smi"

ev.power_limit_w = lambda: 450.0
ev.set_power_limit = fake_set_power_limit
ev._model_id = lambda: "fake-model"

def slow_repetition(*args, **kwargs):
    time.sleep(60.0)

ev.run_repetition = slow_repetition
print(ev.run_stage("E2", "artifact", []), flush=True)
'''


class EvalPowerLimitGuardTest(unittest.TestCase):
    def setUp(self):
        self.calls: list[int] = []
        self._saved = (ev.power_limit_w, ev.set_power_limit, ev._model_id, ev.run_repetition)
        self.addCleanup(self._restore)
        ev._model_id = lambda: "fake-model"
        ev.run_repetition = self._fake_repetition

    def _restore(self):
        (ev.power_limit_w, ev.set_power_limit, ev._model_id, ev.run_repetition) = self._saved

    def _fake_repetition(self, stage, index, artifact_path, model_id, rules, variable):
        return {
            "stage": stage,
            "repetition": index,
            "seeded_cause": ev.SEEDED_RULE,
            "variable": variable,
            "top_rule_id": ev.SEEDED_RULE,
            "verdict": "confirmed",
            "reason": "fake repetition",
            "decode_rate_tok_s": 1.0,
            "spec_tokens_per_forward": 3.0,
            "objective_ratio": 0.5,
        }

    def _setter(self, accepted: set[int]):
        def set_power_limit(watts: int) -> tuple[bool, str]:
            self.calls.append(int(watts))
            return int(watts) in accepted, "fake nvidia-smi"

        return set_power_limit

    def test_e1_all_inconclusive_is_not_a_pass(self):
        """A8: five inconclusive repetitions must not become confirmed."""
        ev.run_repetition = lambda *a: {
            "stage": "E1", "repetition": 1, "seeded_cause": ev.SEEDED_RULE,
            "variable": {}, "top_rule_id": None, "verdict": "inconclusive",
            "reason": "no decode observed", "decode_rate_tok_s": 0.0,
            "spec_tokens_per_forward": 1.0, "objective_ratio": 0.0,
        }
        verdict, note = ev.run_stage("E1", "artifact", [])
        self.assertEqual(verdict, "inconclusive")
        self.assertIn("no usable control repetition", note)

    def test_e2_refuses_a_limit_it_cannot_read_back(self):
        ev.power_limit_w = lambda: None
        ev.set_power_limit = self._setter({ev.TREATMENT_POWER_LIMIT_W})
        verdict, note = ev.run_stage("E2", "artifact", [])
        self.assertEqual(verdict, "inconclusive")
        self.assertEqual(self.calls, [], "the power limit must not be touched")
        self.assertIn("refusing to set it", note)

    def test_e2_restores_the_baseline(self):
        ev.power_limit_w = lambda: 450.0
        ev.set_power_limit = self._setter({ev.TREATMENT_POWER_LIMIT_W, 450})
        verdict, note = ev.run_stage("E2", "artifact", [])
        self.assertEqual(self.calls, [ev.TREATMENT_POWER_LIMIT_W, 450])
        self.assertEqual(verdict, "confirmed")
        self.assertNotIn("NOT restored", note)

    def test_a_failed_restore_is_reported_not_swallowed(self):
        ev.power_limit_w = lambda: 450.0
        ev.set_power_limit = self._setter({ev.TREATMENT_POWER_LIMIT_W})
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            verdict, note = ev.run_stage("E2", "artifact", [])
        self.assertEqual(self.calls, [ev.TREATMENT_POWER_LIMIT_W, 450])
        self.assertIn("NOT restored to 450 W", note)
        self.assertIn("restore failed", error.getvalue())

    def test_a_failed_restore_is_reported_when_a_repetition_raises(self):
        ev.power_limit_w = lambda: 450.0
        ev.set_power_limit = self._setter({ev.TREATMENT_POWER_LIMIT_W})

        def exploding(*args, **kwargs):
            raise RuntimeError("repetition died")

        ev.run_repetition = exploding
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            with self.assertRaises(RuntimeError):
                ev.run_stage("E2", "artifact", [])
        self.assertEqual(self.calls, [ev.TREATMENT_POWER_LIMIT_W, 450])
        self.assertIn("restore failed", error.getvalue())

    def test_a_restore_that_raises_is_reported_before_it_propagates(self):
        """A restore that *raises* used to print nothing at all.

        ``subprocess.run(["sudo", ...])`` raises FileNotFoundError when sudo is
        missing, and the card is still at the treatment value at that moment.
        The note has to reach the operator before the traceback does.
        """
        ev.power_limit_w = lambda: 450.0

        def set_power_limit(watts: int):
            self.calls.append(int(watts))
            if int(watts) == ev.TREATMENT_POWER_LIMIT_W:
                return True, "fake nvidia-smi"
            raise FileNotFoundError("sudo: command not found")

        ev.set_power_limit = set_power_limit
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            with self.assertRaises(FileNotFoundError):
                ev.run_stage("E2", "artifact", [])
        self.assertEqual(self.calls, [ev.TREATMENT_POWER_LIMIT_W, 450])
        self.assertIn("E2 restore failed", error.getvalue())
        self.assertIn("NOT restored to 450 W", error.getvalue())
        self.assertIn("FileNotFoundError", error.getvalue())
        self.assertIn("restore it by hand", error.getvalue())

    def test_a_write_that_raises_after_landing_is_still_restored(self):
        """The guard is armed before the write, so an interrupt cannot skip it.

        ``set_power_limit`` that writes and then raises is `sudo` interrupted
        between the write and its exit: the limit moved and the old code never
        attempted the restore.
        """
        ev.power_limit_w = lambda: 450.0

        def set_power_limit(watts: int):
            self.calls.append(int(watts))
            if int(watts) == ev.TREATMENT_POWER_LIMIT_W:
                raise KeyboardInterrupt("interrupted mid-write")
            return True, "fake nvidia-smi"

        ev.set_power_limit = set_power_limit
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            with self.assertRaises(KeyboardInterrupt):
                ev.run_stage("E2", "artifact", [])
        self.assertEqual(self.calls, [ev.TREATMENT_POWER_LIMIT_W, 450])
        self.assertEqual(error.getvalue(), "")

    def test_the_signal_handler_restores_the_baseline_then_exits(self):
        """SIGTERM does not unwind, so the handler is the only restore path."""
        guard = ev.PowerLimitGuard(self._setter({ev.TREATMENT_POWER_LIMIT_W, 450}))
        guard.arm(450.0)
        previous, ev._ACTIVE_GUARD = ev._ACTIVE_GUARD, guard
        self.addCleanup(setattr, ev, "_ACTIVE_GUARD", previous)
        with self.assertRaises(SystemExit) as caught:
            ev._restore_and_exit(signal.SIGTERM, None)
        self.assertEqual(caught.exception.code, 128 + signal.SIGTERM)
        self.assertEqual(self.calls, [450])
        # The unwinding finally runs a second restore; it must be a no-op.
        self.assertEqual(guard.restore(), "")
        self.assertFalse(guard.armed)
        self.assertEqual(self.calls, [450])

    def test_a_signal_mid_run_restores_the_limit_in_a_real_process(self):
        """End to end: a real signal to a process blocked in a repetition.

        The child's writer is a fake, so the card is never written to. What the
        child records is the order of writes, and an ordinary exit with 128 plus
        the signal number rather than a signal death proves the handler ran and
        restored before exiting -- SIGTERM would otherwise terminate the process
        without unwinding and leave the limit changed.
        """
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum):
                writes, returncode, output = self._signal_a_child(signum)
                self.assertEqual(writes, [str(ev.TREATMENT_POWER_LIMIT_W), "450"], output)
                self.assertEqual(returncode, 128 + signum,
                                 f"the handler did not exit the child: {output}")

    def _signal_a_child(self, signum: int) -> tuple[list[str], int, tuple[str, str]]:
        """Run the child, send it one signal mid-repetition, report what it did."""
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "power-limit-writes.txt"
            log.touch()
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD.format(root=str(root), log=str(log))],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self._wait_for_write(log, str(ev.TREATMENT_POWER_LIMIT_W))
                child.send_signal(signum)
                stdout, stderr = child.communicate(timeout=20.0)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
            return log.read_text(encoding="utf-8").split(), child.returncode, (stdout, stderr)

    @staticmethod
    def _wait_for_write(log: Path, value: str, timeout_s: float = 20.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if value in log.read_text(encoding="utf-8").split():
                return
            time.sleep(0.05)
        raise AssertionError(f"the child never wrote {value} W to {log}")

    def test_e1_never_writes_the_power_limit(self):
        ev.power_limit_w = lambda: 450.0
        ev.set_power_limit = self._setter({ev.TREATMENT_POWER_LIMIT_W})
        ev.run_stage("E1", "artifact", [])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
