import unittest

from adascope.adapters.engines import (
    ENGINE_IDS,
    canonical_name,
    detect_engine,
    strip_prefix,
)


class StripPrefixTest(unittest.TestCase):
    def test_one_known_prefix_is_removed(self):
        self.assertEqual(strip_prefix("llamacpp:tokens_predicted_total"), "tokens_predicted_total")
        self.assertEqual(strip_prefix("ninfer:draft_tokens_total"), "draft_tokens_total")
        self.assertEqual(strip_prefix("vllm:generation_tokens_total"), "generation_tokens_total")
        self.assertEqual(strip_prefix("power_draw_w"), "power_draw_w")


class DetectEngineTest(unittest.TestCase):
    def test_vllm_prefix_wins(self):
        engine, basis = detect_engine({"vllm:generation_tokens_total",
                                       "vllm:num_requests_running"})
        self.assertEqual(engine, "vllm")
        self.assertIn("vllm", basis)

    def test_n_decode_total_is_llamacpp(self):
        engine, _ = detect_engine({
            "llamacpp:tokens_predicted_total",
            "llamacpp:tokens_predicted_seconds_total",
            "llamacpp:n_decode_total",
            "llamacpp:spec_decode_num_drafts_total",
        })
        self.assertEqual(engine, "llamacpp")

    def test_bare_draft_counters_are_ninfer(self):
        engine, _ = detect_engine({
            "llamacpp:tokens_predicted_total",
            "llamacpp:draft_tokens_total",
            "llamacpp:draft_accepted_tokens_total",
        })
        self.assertEqual(engine, "ninfer")

    def test_unrecognised_body_falls_back_to_llamacpp(self):
        engine, basis = detect_engine({"something:else"})
        self.assertEqual(engine, "llamacpp")
        self.assertTrue(basis.startswith("default"))

    def test_empty_body_falls_back_to_llamacpp(self):
        self.assertEqual(detect_engine(set())[0], "llamacpp")


class CanonicalNameTest(unittest.TestCase):
    def test_llamacpp_draft_counters_map_to_canonical(self):
        self.assertEqual(canonical_name("llamacpp", "llamacpp:spec_decode_num_draft_tokens_total"),
                         "draft_tokens_total")
        self.assertEqual(canonical_name("llamacpp",
                                        "llamacpp:spec_decode_num_accepted_tokens_total"),
                         "draft_accepted_tokens_total")
        self.assertEqual(canonical_name("llamacpp", "llamacpp:spec_decode_num_drafts_total"),
                         "draft_rounds_total")

    def test_ninfer_names_are_unchanged(self):
        self.assertEqual(canonical_name("ninfer", "llamacpp:draft_tokens_total"), "draft_tokens_total")
        self.assertEqual(canonical_name("ninfer", "llamacpp:tokens_predicted_total"),
                         "tokens_predicted_total")

    def test_vllm_generation_tokens_map(self):
        self.assertEqual(canonical_name("vllm", "vllm:generation_tokens_total"),
                         "tokens_predicted_total")
        self.assertEqual(canonical_name("vllm", "vllm:num_requests_running"), "num_requests_running")

    def test_unknown_names_pass_through_stripped(self):
        self.assertEqual(canonical_name("llamacpp", "llamacpp:n_busy_slots_per_decode"),
                         "n_busy_slots_per_decode")

    def test_engine_is_validated(self):
        for engine in ("", "mistral", "llamacpp;rm"):
            with self.assertRaises(ValueError, msg=engine):
                canonical_name(engine, "x")
        for engine in ENGINE_IDS:
            self.assertEqual(canonical_name(engine, "x"), "x")


if __name__ == "__main__":
    unittest.main()
