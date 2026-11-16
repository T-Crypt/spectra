import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from adascope.cli import build_parser, main
from adascope.observe import parse_target
from adascope.store import load_run
from tests.fixtures import machine
from tests.support import NO_GPU_REASON, engine_available, engine_down_reason, gpu_available


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

    def test_unknown_engine_is_rejected_before_any_io(self):
        rc = main(["observe", "--target", "127.0.0.1:5804", "--engine", "bogus"])
        self.assertEqual(rc, 2)

    def test_valid_engine_flags_are_accepted_by_the_parser(self):
        for engine in ("auto", "ninfer", "llamacpp", "vllm"):
            args = build_parser().parse_args(["observe", "--target", "127.0.0.1:5804",
                                              "--engine", engine])
            self.assertEqual(args.engine, engine)


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
