import unittest

from adascope.model import Quality
from adascope.reference import dense_decode_reference, load_profile

RECORDED_ARTIFACT_BYTES = 18210531328
PRE_SPEC_CEILING = 1008e9 / RECORDED_ARTIFACT_BYTES  # 55.3526 tok/s


class ReferenceTest(unittest.TestCase):
    def test_pre_spec_ceiling_matches_derived_value(self):
        ref = dense_decode_reference(
            artifact_bytes=RECORDED_ARTIFACT_BYTES,
            bandwidth_gbps=1008.0,
            spec_tokens_per_forward=1.0,
        )
        self.assertAlmostEqual(ref.ceiling, 55.4, delta=0.1)
        self.assertIs(ref.quality, Quality.DERIVED)
        self.assertIn("artifact_bytes", ref.derivation["inputs"])
        self.assertIn("bandwidth_gbps", ref.derivation["inputs"])
        self.assertIn("spec_tokens_per_forward", ref.derivation["inputs"])

    def test_ceiling_is_linear_in_the_factor(self):
        # The model is pinned as arithmetic, not as a blessing of one factor.
        for factor in (1.6635, 1.97, 3.0195):
            ref = dense_decode_reference(
                artifact_bytes=RECORDED_ARTIFACT_BYTES,
                bandwidth_gbps=1008.0,
                spec_tokens_per_forward=factor,
            )
            self.assertAlmostEqual(ref.ceiling, PRE_SPEC_CEILING * factor, delta=0.01)

    def test_implied_factor_197_reproduces_the_observed_rate_arithmetic_only(self):
        """A9: 1.97 is 109.1 / 55.3526, the factor implied by the rate it predicts.

        It is an arithmetic identity, never a derived input. The analyser
        derives its factor from the run's counters by the round rule.
        """
        ref = dense_decode_reference(
            artifact_bytes=RECORDED_ARTIFACT_BYTES,
            bandwidth_gbps=1008.0,
            spec_tokens_per_forward=109.0954 / PRE_SPEC_CEILING,
        )
        self.assertAlmostEqual(ref.ceiling, 109.0954, delta=0.01)
        self.assertAlmostEqual(ref.ceiling, 109.0, delta=1.0)

    def test_profile_carries_documented_values_and_kv_term(self):
        profile = load_profile()
        self.assertEqual(profile["mem_bandwidth_spec_gbps"], 1008)
        self.assertEqual(profile["sm_count"], 128)
        self.assertEqual(profile["l2_bytes"], 75497472)
        self.assertEqual(profile["pcie_link_gen"], 4)
        self.assertEqual(profile["pcie_link_width"], 16)
        self.assertEqual(profile["clock_sm_max_mhz"], 3135)
        self.assertEqual(profile["clock_mem_max_mhz"], 10501)
        self.assertEqual(profile["arch"], "sm_89")
        ref = dense_decode_reference(
            artifact_bytes=1000,
            kv_bytes_per_token=2.0,
            context_tokens=100,
            bandwidth_gbps=1008.0,
        )
        self.assertAlmostEqual(ref.ceiling, 1008e9 / (1000 + 2.0 * 100), places=6)


if __name__ == "__main__":
    unittest.main()
