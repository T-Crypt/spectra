import json
import tempfile
import unittest

from adascope.adapters.ncu import NcuAdapter
from adascope.adapters.nsys import NsysAdapter, profiling_overhead


class NsysNcuTest(unittest.TestCase):
    def test_nsys_csv_import(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("name,dur\nkernel_a,100\nkernel_b,200\n")
            path = f.name
        adapter = NsysAdapter(path)
        events = adapter.import_events()
        self.assertEqual(len(events), 2)
        summary = adapter.kernel_summary()
        self.assertEqual(summary[0]["name"], "kernel_b")
        self.assertAlmostEqual(profiling_overhead(10.0, 12.0), 0.2)

    def test_nsys_json_import(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([{"name": "k", "duration_ns": 5}], f)
            path = f.name
        adapter = NsysAdapter(path)
        self.assertEqual(len(adapter.import_events()), 1)

    def test_ncu_csv_import(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("Kernel,Metric Name,Metric Value\nk,sm__throughput,50.0\n")
            path = f.name
        adapter = NcuAdapter(path)
        metrics = adapter.import_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(adapter.metric_value("k", "sm__throughput"), 50.0)
