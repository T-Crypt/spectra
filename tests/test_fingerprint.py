import unittest

from adascope.fingerprint import compare_runs, fingerprint, fingerprint_id
from adascope.reference import load_profile
from tests.fixtures import recorded_run as fixtures


def profile():
    return load_profile()


class FingerprintTest(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        run = fixtures.recorded_run()
        fp1 = fingerprint(run)
        fp2 = fingerprint(run)
        self.assertEqual(fp1, fp2)
        self.assertEqual(fingerprint_id(fp1), fingerprint_id(fp2))

    def test_compare_identical_runs_is_comparable(self):
        run = fixtures.recorded_run()
        result = compare_runs(run, run, profile())
        self.assertEqual(result.verdict.value, "comparable")
        self.assertEqual(result.config_diff, [])

    def test_compare_different_config_is_comparable_with_normalization_or_comparable(self):
        a = fixtures.recorded_run()
        b = fixtures.recorded_run()
        b.workload.config = {"x": 1}
        a.workload.config = {"x": 2}
        result = compare_runs(a, b, profile())
        self.assertIn(result.verdict.value, ("comparable", "comparable_with_normalization"))
        self.assertEqual(len(result.config_diff), 1)
        self.assertEqual(result.config_diff[0]["key"], "x")

    def test_compare_different_model_is_not_comparable(self):
        a = fixtures.recorded_run()
        b = fixtures.recorded_run()
        b.workload.model_id = "other"
        b.workload.artifact_bytes = 1
        result = compare_runs(a, b, profile())
        self.assertEqual(result.verdict.value, "not_comparable")

    def test_metric_deltas_present(self):
        a = fixtures.recorded_run()
        b = fixtures.treatment_run() if hasattr(fixtures, "treatment_run") else a
        result = compare_runs(a, b, profile())
        self.assertIn("decode_rate_tok_s", result.metric_deltas)
