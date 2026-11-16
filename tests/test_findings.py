import tempfile
import unittest

from adascope.model import Finding, FindingVerdict
from adascope.store import list_findings, load_finding, query_findings, save_finding


class FindingsTest(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            finding = Finding(id="f1", hypothesis_id="h1", verdict=FindingVerdict.CONFIRMED,
                             arch="sm_89", engine_id="ninfer", workload_class="dense-decode",
                             variable="power_limit_w", direction="maximize")
            path = save_finding(finding, d)
            loaded = load_finding(path)
            self.assertEqual(loaded.id, "f1")
            self.assertEqual(loaded.verdict, FindingVerdict.CONFIRMED)

    def test_query_findings(self):
        with tempfile.TemporaryDirectory() as d:
            f1 = Finding(id="f1", hypothesis_id="h1", verdict=FindingVerdict.CONFIRMED,
                         arch="sm_89", engine_id="ninfer", workload_class="dense-decode",
                         variable="power_limit_w", direction="maximize")
            f2 = Finding(id="f2", hypothesis_id="h2", verdict=FindingVerdict.REJECTED,
                         arch="sm_89", engine_id="ninfer", workload_class="dense-decode",
                         variable="x", direction="minimize")
            save_finding(f1, d)
            save_finding(f2, d)
            res = query_findings(d, variable="power_limit_w")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0].id, "f1")
            res2 = query_findings(d, verdict="rejected")
            self.assertEqual(len(res2), 1)

    def test_list_findings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(list_findings(d), [])
