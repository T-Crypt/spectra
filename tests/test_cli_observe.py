import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from adascope.cli import main
from adascope.adapters.lmcompat import parse_jsonl_lines
from adascope.observe import _request_series, parse_target
from adascope.store import load_run
from tests.fixtures import machine
from tests.support import NO_GPU_REASON, engine_available, engine_down_reason, gpu_available

START_MS = 1_760_000_000_000
END_MS = 1_760_000_100_000


def _request(timestamp_ms, instance, completion, decode, rounds):
    return json.dumps({
        "schema_version": 20,
        "event": "request_done",
        "timestamp_unix_ms": timestamp_ms,
        "server_instance_id": instance,
        "result": {"completion_tokens": completion},
        "timings_seconds": {"decode": decode},
        "speculative": {"rounds": rounds},
    })


SERVER_START = json.dumps({
    "schema_version": 20,
    "event": "server_start",
    "timestamp_unix_ms": START_MS,
    "server_instance_id": "5d2a",
})


class ObserveBoundaryTest(unittest.TestCase):
    def test_target_parses_and_rejects(self):
        self.assertEqual(parse_target("127.0.0.1:5804"), ("127.0.0.1", 5804))
        for bad in ("nope", "host:", ":123", "host:99999", "host:abc"):
            with self.assertRaises(ValueError, msg=bad):
                parse_target(bad)

    def test_duration_and_hz_are_rejected_before_any_io(self):
        for flag, value in (("--duration", "0"), ("--hz", "0")):
            rc = main(["observe", "--target", "127.0.0.1:5804", flag, value])
            self.assertEqual(rc, 2, f"{flag} {value}")

    def test_config_file_must_hold_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(["not", "an", "object"]))
            rc = main(["observe", "--target", "127.0.0.1:5804", "--duration", "2", "--config", str(path)])
            self.assertEqual(rc, 2)

    def test_unwired_command_exits_non_zero(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["frobnicate"])
        self.assertNotEqual(caught.exception.code, 0)


class RequestSeriesTest(unittest.TestCase):
    """``observe``'s per-request series: the JSONL-only live path.

    ``_request_series`` is the only place that turns parsed request records into
    the ``request_decode_*`` series the analysis reads. It was reachable only
    from a live ``observe`` run, so its window and instance filters had no test
    that runs without the engine.
    """

    def test_only_the_current_instance_inside_the_window_is_kept(self):
        lines = [
            SERVER_START,
            _request(START_MS - 1_000, "5d2a", 50, 1.0, 12),   # before the window
            _request(START_MS + 50_000, "ffff", 30, 2.0, 10),  # another instance
            _request(START_MS + 200_000, "5d2a", 60, 1.0, 12),  # after the window
            _request(START_MS + 50_000, "5d2a", 40, 1.5, 13),  # kept
        ]
        series = _request_series(parse_jsonl_lines(lines), START_MS, END_MS)
        self.assertEqual([s.metric for s in series],
                         ["request_decode_tokens", "request_decode_seconds", "request_decode_rounds"])
        self.assertEqual(series[0].samples, [(50.0, 39.0)])  # completion_tokens - 1
        self.assertEqual(series[1].samples, [(50.0, 1.5)])
        self.assertEqual(series[2].samples, [(50.0, 13.0)])

        # No server_start record means no instance to filter on: every
        # in-window request is kept and the series stay cumulative.
        loose = [
            _request(START_MS + 50_000, "aaaa", 40, 1.5, 13),
            _request(START_MS + 60_000, "bbbb", 20, 1.0, 5),
        ]
        series = _request_series(parse_jsonl_lines(loose), START_MS, END_MS)
        self.assertEqual(series[0].samples, [(50.0, 39.0), (60.0, 58.0)])


@unittest.skipUnless(gpu_available(), NO_GPU_REASON)
class ObserveLiveTest(unittest.TestCase):
    def test_observe_writes_loadable_run(self):
        port = machine.resolve_engine_port()
        if not engine_available(machine.ENGINE_HOST, port):
            self.skipTest(engine_down_reason(machine.ENGINE_HOST, port))
        artifact = machine.LIVE_ARTIFACT_PATH
        if not os.path.isfile(artifact):
            self.skipTest(machine.missing_artifact_reason(artifact))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "smoke.json"
            rc = main([
                "observe",
                "--target", f"{machine.ENGINE_HOST}:{port}",
                "--duration", "2",
                "--hz", "2",
                "--artifact", artifact,
                "--out", str(out),
            ])
            self.assertEqual(rc, 0)
            run = load_run(out)
            self.assertIn("nvml", run.sources)
            hw_series = [s for s in run.series if s.source == "nvml"]
            self.assertTrue(hw_series)
            for series in hw_series:
                self.assertGreaterEqual(len(series.samples), 3)
            self.assertEqual(run.workload.artifact_bytes, os.path.getsize(artifact))


if __name__ == "__main__":
    unittest.main()
