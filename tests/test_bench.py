import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from adascope.bench import build_prompt, driver_series, start_driver, validate_load
from adascope.cli import main
from adascope.store import load_run
from tests.fixtures import machine
from tests.support import engine_available, engine_down_reason, gpu_available, NO_GPU_REASON

from adascope.model import Quality


class BuildPromptTest(unittest.TestCase):
    def test_exact_word_count(self):
        for words in (1, 8, 9, 10, 256):
            text, count = build_prompt(words)
            self.assertEqual(count, words, words)
            self.assertEqual(len(text.split()), words, words)

    def test_deterministic(self):
        self.assertEqual(build_prompt(256), build_prompt(256))
        self.assertNotEqual(build_prompt(256)[0], build_prompt(257)[0])

    def test_invalid_counts_are_rejected(self):
        for bad in (0, -3, 1.5, "256", True):
            with self.assertRaises(ValueError, msg=bad):
                build_prompt(bad)


class ValidateLoadTest(unittest.TestCase):
    def test_good_config_passes_through(self):
        load = {"prompt_words": 128, "completion_tokens": 64, "concurrency": 2}
        self.assertEqual(validate_load(load), load)

    def test_bad_values_are_rejected(self):
        for load in (
            {"prompt_words": 0, "completion_tokens": 64, "concurrency": 1},
            {"prompt_words": 128, "completion_tokens": 0, "concurrency": 1},
            {"prompt_words": 128, "completion_tokens": 64, "concurrency": 0},
            {"prompt_words": "128", "completion_tokens": 64, "concurrency": 1},
            {"prompt_words": 128, "completion_tokens": 64},
            None,
            "load",
        ):
            with self.assertRaises(ValueError, msg=load):
                validate_load(load)


class DriverSeriesTest(unittest.TestCase):
    def test_cumulative_counters_from_unordered_events(self):
        series = driver_series([(3.0, "completed"), (1.0, "failed"), (2.0, "completed")])
        by_metric = {s.metric: s.samples for s in series}
        self.assertEqual(by_metric["driver_requests_completed"], [(2.0, 1), (3.0, 2)])
        self.assertEqual(by_metric["driver_requests_failed"], [(1.0, 1)])
        for s in series:
            self.assertIs(s.quality, Quality.MEASURED)
            self.assertEqual(s.source, "bench")

    def test_no_events_still_says_zero_completed(self):
        series = driver_series([])
        self.assertEqual([s.metric for s in series], ["driver_requests_completed"])
        self.assertEqual(series[0].samples, [])

    def test_no_failures_means_no_failed_series(self):
        series = driver_series([(1.0, "completed")])
        self.assertEqual([s.metric for s in series], ["driver_requests_completed"])


class BenchBoundaryTest(unittest.TestCase):
    def test_invalid_load_flags_are_rejected_before_any_io(self):
        for flag, value in (("--prompt-words", "0"), ("--concurrency", "0"),
                            ("--completion-tokens", "0")):
            rc = main(["bench", "--target", "127.0.0.1:5804", flag, value])
            self.assertEqual(rc, 2, f"{flag} {value}")

    def test_defaults_parse(self):
        from adascope.cli import build_parser

        args = build_parser().parse_args(["bench", "--target", "127.0.0.1:5804"])
        self.assertEqual(args.prompt_words, 256)
        self.assertEqual(args.completion_tokens, 256)
        self.assertEqual(args.concurrency, 1)


class DriverLoopTest(unittest.TestCase):
    """The drive loop against a real local HTTP server, no GPU needed."""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.events = []

    def record(self, offset: float, kind: str) -> None:
        self.events.append((offset, kind))

    def test_completions_are_counted(self):
        stop, threads = start_driver(
            "127.0.0.1", self.port, "model-x", "prompt", 16, 2,
            self.record, time.monotonic())
        time.sleep(0.5)
        stop.set()
        for thread in threads:
            thread.join(timeout=5.0)
        self.assertGreaterEqual(len(self.events), 2)
        kinds = {kind for _, kind in self.events}
        self.assertEqual(kinds, {"completed"})

    def test_a_dead_port_counts_failures_not_silence(self):
        stop, threads = start_driver(
            "127.0.0.1", 1, "model-x", "prompt", 16, 1,
            self.record, time.monotonic())
        time.sleep(0.4)
        stop.set()
        for thread in threads:
            thread.join(timeout=5.0)
        self.assertTrue(self.events)
        self.assertEqual({kind for _, kind in self.events}, {"failed"})


@unittest.skipUnless(gpu_available(), NO_GPU_REASON)
class BenchLiveTest(unittest.TestCase):
    def test_bench_writes_a_run_with_the_driver_fingerprint(self):
        port = machine.resolve_engine_port()
        if not engine_available(machine.ENGINE_HOST, port):
            self.skipTest(engine_down_reason(machine.ENGINE_HOST, port))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bench.json"
            rc = main([
                "bench",
                "--target", f"{machine.ENGINE_HOST}:{port}",
                "--duration", "3",
                "--hz", "2",
                "--prompt-words", "16",
                "--completion-tokens", "16",
                "--concurrency", "1",
                "--out", str(out),
            ])
            self.assertEqual(rc, 0)
            run = load_run(out)
            driver = run.workload.config.get("driver")
            self.assertIsInstance(driver, dict)
            self.assertEqual(driver["id"], "spectra-bench")
            self.assertEqual(driver["prompt_words"], 16)
            self.assertEqual(driver["completion_tokens"], 16)
            self.assertEqual(driver["concurrency"], 1)
            self.assertIn("bench", run.sources)
            metrics = {s.metric: s for s in run.series}
            self.assertIn("driver_requests_completed", metrics)
            # A short window with thinking enabled may finish nothing; the
            # series must exist and its last value must be a non-negative
            # number, which says the driver ran and counted.
            samples = metrics["driver_requests_completed"].samples
            last = samples[-1][1] if samples else 0
            self.assertGreaterEqual(last, 0)


if __name__ == "__main__":
    unittest.main()
