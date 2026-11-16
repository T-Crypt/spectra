import json
import tempfile
import unittest

from adascope.adapters.cuda import build_run, load_series
from adascope.assist import draft_hypotheses, summarize_report


class CudaAssistTest(unittest.TestCase):
    def test_load_series_and_build_run(self):
        data = {
            "hardware": {
                "name": "GPU", "arch": "sm_89", "compute_capability": "8.9",
                "vram_total_bytes": 1000,
            },
            "series": [
                {"metric": "throughput", "unit": "op/s", "samples": [[0.0, 1.0], [1.0, 2.0]]},
            ],
            "workload": {"engine_id": "cuda", "artifact_bytes": 10},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        series = load_series(path)
        self.assertEqual(len(series), 1)
        run = build_run(path)
        self.assertEqual(run.workload.adapter_id, "cuda")
        self.assertEqual(run.series[0].metric, "throughput")

    def test_assist_drafts_hypotheses(self):
        drafts = draft_hypotheses("run-1", {"co_tenant": True, "power_ratio": 0.99})
        self.assertTrue(all(h.confidence.value == "hypothesis" for h in drafts))
        self.assertTrue(any("co-tenant" in h.claim for h in drafts))

    def test_assist_summarize_fallback(self):
        text = "Run: abc\nWorkload: x"
        self.assertEqual(summarize_report(text), "Run: abc")
