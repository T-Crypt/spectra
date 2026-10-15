import time
import unittest

from adascope.adapters.lmcompat import (
    LmCompat,
    parse_jsonl_lines,
    parse_metrics_text,
    strip_known_prefix,
)
from tests.fixtures import machine
from tests.support import engine_available, engine_down_reason

HOST = machine.ENGINE_HOST
PORT = machine.resolve_engine_port()

REQUEST_DONE = (
    '{"schema_version": 20, "event": "request_done", "timestamp_unix_ms": 1760000100000,'
    ' "server_instance_id": "5d2a",'
    ' "result": {"completion_tokens": 40},'
    ' "timings_seconds": {"prepare": 0.1, "ttft": 0.2, "decode": 1.5, "total": 1.8},'
    ' "speculative": {"draft_window": 3, "rounds": 13, "drafted_tokens": 39,'
    ' "accepted_tokens": 27}}'
)
SERVER_START = (
    '{"schema_version": 20, "event": "server_start", "timestamp_unix_ms": 1760000000000,'
    ' "server_instance_id": "5d2a",'
    ' "artifact": {"path": "/home/tcrypt/ninfer-v3-artifacts/qwen3_8_27b.v3.ninfer",'
    ' "size_bytes": 18210749936},'
    ' "engine": {"speculative_draft_window": 3, "max_context": 262144, "max_concurrency": 1},'
    ' "argv": ["ninfer", "--spec", "mtp"]}'
)


class PrometheusParserTest(unittest.TestCase):
    def test_parser_keeps_full_names_and_adds_no_alias(self):
        body = (
            "# HELP llamacpp:tokens_predicted_total total\n"
            'llamacpp:tokens_predicted_total{model="x"} 65329\n'
            "ninfer:draft_accepted_tokens_total 43693\n"
        )
        parsed = parse_metrics_text(body)
        self.assertEqual(parsed["llamacpp:tokens_predicted_total"], 65329)
        self.assertEqual(parsed["ninfer:draft_accepted_tokens_total"], 43693)
        self.assertNotIn("tokens_predicted_total", parsed)
        self.assertNotIn("draft_accepted_tokens_total", parsed)

    def test_strip_known_prefix(self):
        self.assertEqual(strip_known_prefix("llamacpp:tokens_predicted_total"), "tokens_predicted_total")
        self.assertEqual(strip_known_prefix("ninfer:draft_tokens_total"), "draft_tokens_total")
        self.assertEqual(strip_known_prefix("power_draw_w"), "power_draw_w")


class JsonlReaderTest(unittest.TestCase):
    def test_v20_records_are_read_and_junk_is_ignored(self):
        """The literals below are the shape the engine writes, not its output.

        ``event_base`` and ``request_done`` were read out of the engine source
        (``request_log.cpp``), so this proves the reader handles that shape: it
        does not prove the engine emits it, which only a live log can. The
        reader tolerates every missing key for the same reason.
        """
        summary = parse_jsonl_lines([REQUEST_DONE, "not json at all", SERVER_START, ""])
        self.assertEqual(summary.schema_version, 20)
        self.assertEqual(summary.request_count, 1)
        request = summary.requests[0]
        self.assertEqual(request.completion_tokens, 40)
        self.assertEqual(request.decode_seconds, 1.5)
        self.assertEqual(request.rounds, 13)
        self.assertEqual(request.drafted_tokens, 39)
        self.assertEqual(request.accepted_tokens, 27)
        self.assertEqual(request.draft_window, 3)
        self.assertEqual(request.timestamp_unix_ms, 1760000100000)
        self.assertEqual(request.server_instance_id, "5d2a")
        # Configuration is stored whole, not summarised.
        self.assertEqual(summary.server_start["artifact"]["size_bytes"], 18210749936)
        self.assertEqual(summary.server_start["engine"]["max_context"], 262144)
        self.assertEqual(summary.artifact_size_bytes(), 18210749936)
        self.assertEqual(summary.server_instance_id, "5d2a")

    def test_v19_record_yields_an_empty_summary(self):
        v19 = '{"schema_version": 19, "type": "request_done", "timings": {"predicted_per_second": 108.4}}'
        summary = parse_jsonl_lines([v19])
        self.assertEqual(summary.request_count, 0)
        self.assertEqual(summary.config, {})
        self.assertIsNone(summary.artifact_size_bytes())

    def test_a_different_schema_version_is_not_read_as_v20(self):
        """A4: the gate is the version, not the absence of keys.

        A v22 record that keeps every v20 key would otherwise be read as v20
        silently. The whole file is dropped, including records already read, so
        a log from two engine builds is never mixed into one summary.
        v21 is accepted: its request_done keys were verified against the live
        engine on 2026-10-15.
        """
        v21 = ('{"schema_version": 22, "event": "request_done",'
               ' "result": {"completion_tokens": 5}, "timings_seconds": {"decode": 1.0}}')
        summary = parse_jsonl_lines([v21])
        self.assertEqual(summary.request_count, 0)
        self.assertIsNone(summary.schema_version)
        summary = parse_jsonl_lines([REQUEST_DONE, SERVER_START, v21])
        self.assertEqual(summary.request_count, 0)
        self.assertEqual(summary.config, {})
        self.assertIsNone(summary.schema_version)

    def test_a_record_without_a_decode_time_is_skipped(self):
        """A non-positive decode time is not a measurement."""
        for decode in ("0", "-1.5"):
            with self.subTest(decode=decode):
                line = ('{"schema_version": 20, "event": "request_done",'
                        ' "result": {"completion_tokens": 40},'
                        f' "timings_seconds": {{"decode": {decode}}}}}')
                self.assertEqual(parse_jsonl_lines([line]).request_count, 0)


@unittest.skipUnless(engine_available(HOST, PORT), engine_down_reason(HOST, PORT))
class LmCompatLiveTest(unittest.TestCase):
    def test_metrics_carries_predicted_counters(self):
        client = LmCompat(HOST, PORT)
        try:
            first = client.metrics()
        except Exception as exc:
            self.skipTest(f"the backend exposes no /metrics: {exc}")
        self.assertIn("llamacpp:tokens_predicted_total", first)
        self.assertGreaterEqual(first["llamacpp:tokens_predicted_total"], 0)
        time.sleep(1.0)
        second = client.metrics()
        self.assertGreaterEqual(
            second["llamacpp:tokens_predicted_seconds_total"],
            first["llamacpp:tokens_predicted_seconds_total"],
        )

    def test_models_lists_ninfer_model(self):
        client = LmCompat(HOST, PORT)
        ids = [str(m.get("id", "")) for m in client.models()]
        self.assertTrue(any("NInfer" in mid for mid in ids), ids)


if __name__ == "__main__":
    unittest.main()
