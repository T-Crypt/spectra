"""Acceptance tests: what fixtures can carry, and what needs the engine.

Criteria from docs/EVAL.md (d):

- A1 reproducibility: render a stored fixture run twice, byte-identical, across
  the store as well as in memory. Runs today.
- A2 fidelity, fixture half: from the recorded-counter fixture plus the
  per-request series, the derived decode rate and the token-weighted
  per-request rate agree within one percent. Runs today; the test docstring
  says exactly what it does and does not prove.
- A2 fidelity, live half: needs the engine up, ``SPECTRA_LIVE_FIDELITY=1`` and a
  request log. Skips with the reason otherwise.
- A2 third instrument: the HTTP reply's own ``timings.predicted_per_second``,
  which has a different denominator and is recorded as a separate, weaker check
  rather than folded into A2's one percent.

The other criteria live where they can run: A3 in tests/test_reference.py, A4,
A5, A6 and A8 in tests/eval_induced_bottleneck.py, A7 in tests/test_report.py,
A9 in tests/test_analyze.py.
"""

import os
import tempfile
import threading
import unittest
from pathlib import Path

from adascope.adapters.lmcompat import LmCompat
from adascope.analyze import facts_from_run
from adascope.cli import main
from adascope.engine import default_rules_path, load_rules
from adascope.reference import load_profile
from adascope.report import render
from adascope.store import load_run, save_run
from tests.fixtures import machine, recorded_run as fixtures
from tests.support import engine_available, engine_down_reason

LIVE_FIDELITY_ENV = "SPECTRA_LIVE_FIDELITY"
LIVE_JSONL_ENV = "SPECTRA_LIVE_JSONL"


def rules():
    return load_rules(default_rules_path())


def engine_is_up() -> bool:
    return engine_available(machine.ENGINE_HOST, machine.resolve_engine_port())


class AcceptanceFixtureTest(unittest.TestCase):
    def test_a1_rendering_a_stored_run_is_reproducible(self):
        run = fixtures.recorded_run()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_run(run, tmp)
            stored = load_run(path)
            first = render(stored, load_profile(), rules())
            self.assertEqual(first, render(stored, load_profile(), rules()))
            self.assertEqual(first, render(run, load_profile(), rules()))

    def test_a2_counter_rate_and_per_request_rate_agree(self):
        """What this proves, and what it does not.

        The counters are the real readings recorded in docs/MILESTONE-1.md. The
        per-request series are built to the verified schema v20 shape, with the
        token-weighted aggregate over the steady window equal to what the
        counters give. So this proves the aggregation, the window handling and
        the label. It does not prove that the engine's two producers agree: the
        counter path sums decode-round wall time and the per-request path sums
        per-request decode time, so they are not two independent instruments.
        The live half proves the aggregation on a real file; the HTTP reply's
        own rate in the third test is the one genuinely independent instrument.
        """
        facts = facts_from_run(fixtures.recorded_run(), load_profile())
        derived = facts["decode_rate_tok_s"]
        per_request = facts["engine_request_rate_tok_s"]
        self.assertGreater(per_request, 0.0)
        self.assertLessEqual(abs(derived - per_request), 0.01 * per_request)


@unittest.skipUnless(os.environ.get(LIVE_FIDELITY_ENV) == "1",
                     f"opt-in: set {LIVE_FIDELITY_ENV}=1 to run the live fidelity checks")
class AcceptanceLiveTest(unittest.TestCase):
    def _driver(self):
        try:
            from tests import load
        except Exception as exc:  # pragma: no cover - depends on the tree
            self.skipTest(f"no load driver: tests/load.py is not importable ({exc})")
        return load

    def _model_id(self, client: LmCompat) -> str:
        models = client.models()
        if not models:
            self.skipTest("the engine lists no model")
        return str(models[0].get("id", ""))

    def test_a2_live_fidelity_against_per_request_decode_time(self):
        port = machine.resolve_engine_port()
        if not engine_is_up():
            self.skipTest(engine_down_reason(machine.ENGINE_HOST, port))
        jsonl = os.environ.get(LIVE_JSONL_ENV, "")
        if not jsonl:
            self.skipTest(
                "no request log: the engine was not launched with --request-log-jsonl, "
                "so per-request decode time cannot be measured"
            )
        driver = self._driver()
        client = LmCompat(machine.ENGINE_HOST, port)
        model_id = self._model_id(client)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "live.json"
            stop = threading.Event()
            thread = threading.Thread(
                target=driver.drive_decode,
                args=(machine.ENGINE_HOST, port, model_id, stop),
                daemon=True,
            )
            thread.start()
            try:
                rc = main([
                    "observe",
                    "--target", f"{machine.ENGINE_HOST}:{port}",
                    "--duration", "30",
                    "--hz", "2",
                    "--artifact", machine.LIVE_ARTIFACT_PATH,
                    "--metrics-jsonl", jsonl,
                    "--out", str(out),
                ])
            finally:
                stop.set()
                thread.join(timeout=5.0)
            self.assertEqual(rc, 0)
            facts = facts_from_run(load_run(out), load_profile())
        per_request = facts["engine_request_rate_tok_s"]
        if per_request is None:
            self.skipTest("no decode observed in the window: the request log held no request_done record")
        derived = facts["decode_rate_tok_s"]
        self.assertLessEqual(abs(derived - per_request), 0.01 * per_request)

    def test_a2_third_instrument_is_the_http_reply(self):
        """The engine's own rate over the wall clock, not a second view of one file.

        ``timings.predicted_per_second`` is ``(generated_tokens - 1) / generation_ms``
        over the wall clock between the first and the last token, while the
        JSONL's ``timings_seconds.decode`` accumulates decode time. The two
        denominators differ, so this test prints the gap and asserts only that
        both numbers are positive.
        """
        port = machine.resolve_engine_port()
        if not engine_is_up():
            self.skipTest(engine_down_reason(machine.ENGINE_HOST, port))
        driver = self._driver()
        client = LmCompat(machine.ENGINE_HOST, port, timeout_s=600.0)
        model_id = self._model_id(client)
        try:
            counters_before = client.metrics()
        except Exception as exc:
            self.skipTest(f"the backend exposes no /metrics: {exc}")
        try:
            reply = driver.stream_completion(machine.ENGINE_HOST, port, model_id,
                                             max_tokens=64)
        except OSError as exc:
            # An engine that answers /health but refuses the completion request is
            # unreachable for this check, not a failure of the check: skip it, as
            # the module's other network tests do. HTTPError is an OSError.
            self.skipTest(f"the engine refused the completion request: {exc}")
        counters_after = client.metrics()
        timings = reply.get("timings") if isinstance(reply, dict) else None
        per_request = timings.get("predicted_per_second") if isinstance(timings, dict) else None
        if not isinstance(per_request, (int, float)):
            self.skipTest("the reply carried no timings.predicted_per_second")
        tokens = (counters_after.get("llamacpp:tokens_predicted_total", 0.0)
                  - counters_before.get("llamacpp:tokens_predicted_total", 0.0))
        seconds = (counters_after.get("llamacpp:tokens_predicted_seconds_total", 0.0)
                   - counters_before.get("llamacpp:tokens_predicted_seconds_total", 0.0))
        derived = (tokens / seconds) if seconds > 0 else 0.0
        gap = abs(derived - float(per_request))
        print(f"http reply {float(per_request):.1f} tok/s vs counters {derived:.1f} tok/s, gap {gap:.1f}")
        self.assertGreater(float(per_request), 0.0)
        self.assertGreater(derived, 0.0)


if __name__ == "__main__":
    unittest.main()
