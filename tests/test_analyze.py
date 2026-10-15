import unittest

from adascope.analyze import (
    facts_from_run,
    hypotheses_from_run,
    observations_from_run,
    rank,
)
from adascope.engine import default_rules_path, fires, load_rules
from adascope.model import Quality
from tests.fixtures import recorded_run as fixtures


def rules():
    return load_rules(default_rules_path())


def profile():
    return {"mem_bandwidth_spec_gbps": 1008.0}


class AnalyzeTest(unittest.TestCase):
    def test_facts_match_literal_values(self):
        facts = facts_from_run(fixtures.crafted_run(), profile())
        self.assertAlmostEqual(facts["power_ratio"], 445.0 / 450.0, places=4)
        self.assertAlmostEqual(facts["decode_rate_tok_s"], 47.5, places=4)
        self.assertEqual(facts["temp_c"], 63.0)
        self.assertTrue(facts["throttle.sw_power_cap"])
        self.assertIs(observations_from_run(fixtures.crafted_run())[0].metric, "power_draw_mean_w")

    def test_recorded_counters_reproduce_e0(self):
        # E0: the recorded counters, no GPU and no server.
        run = fixtures.recorded_run()
        facts = facts_from_run(run, profile())
        self.assertAlmostEqual(facts["decode_rate_tok_s"], 109.0954, delta=0.01)
        self.assertAlmostEqual(facts["spec_tokens_per_forward"], 3.0195, delta=0.03)
        self.assertAlmostEqual(facts["reference_ceiling_tok_s"], 167.1348, delta=1.0)
        self.assertAlmostEqual(facts["objective_ratio"], 0.6527, delta=0.003)
        self.assertTrue(facts["model_consistent"])
        self.assertEqual(facts["spec_method"],
                         "committed/(committed-accepted): tokens per decode forward pass")
        ranked = hypotheses_from_run(run, profile(), rules())
        self.assertEqual([h.rules[0] for h in ranked], [])

    def test_inconsistent_run_is_flagged(self):
        # A9: a run whose own counters exceed the ceiling it derived.
        facts = facts_from_run(fixtures.inconsistent_run(), profile())
        self.assertGreater(facts["objective_ratio"], 1.0)
        self.assertFalse(facts["model_consistent"])
        self.assertEqual(facts["spec_tokens_per_forward"], 1.0)
        self.assertEqual(facts["spec_method"], "no draft counters; no speculation assumed")
        fired = [r["id"] for r in rules() if fires(r, facts)]
        self.assertNotIn("sm89.decode-near-bandwidth-roof", fired)

    def test_treatment_run_ranks_the_power_cap_first(self):
        run = fixtures.treatment_run()
        ranked = hypotheses_from_run(run, profile(), rules())
        self.assertEqual([h.rules[0] for h in ranked], ["sm89.power-cap-limit"])
        self.assertIs(ranked[0].confidence, Quality.MEASURED)
        self.assertEqual(ranked[0].evidence, ["power_draw_mean_w"])
        self.assertEqual([h.rules[0] for h in ranked[0].alternatives], ["sm89.thermal-throttle"])
        self.assertIs(ranked[0].alternatives[0].confidence, Quality.HYPOTHESIS)

    def test_roof_rule_fires_and_its_evidence_resolves(self):
        """The one rule whose declared evidence is a derived fact.

        ``decode_rate_tok_s`` is a delta ratio, not the summary of one series,
        so it is a fact rather than an observation. If nothing resolves it the
        hypothesis renders with no basis at all, which is how the defect this
        test guards got in: no test exercised a roof-rule firing.
        """
        run = fixtures.roof_run()
        facts = facts_from_run(run, profile())
        self.assertGreaterEqual(facts["objective_ratio"], 0.9)
        self.assertLessEqual(facts["objective_ratio"], 1.0)
        ranked = hypotheses_from_run(run, profile(), rules())
        self.assertEqual([h.rules[0] for h in ranked], ["sm89.decode-near-bandwidth-roof"])
        self.assertEqual(ranked[0].evidence, ["decode_rate_tok_s"])

    def test_a_series_with_no_delta_has_no_rate(self):
        """The sentinel is 0.0, and the availability flag says so.

        facts_from_run keeps the plan's 0.0 sentinel; what a consumer must read
        before printing it is ``decode_rate_available``. The renderer's half of
        this is tests/test_report.py.
        """
        facts = facts_from_run(fixtures.one_sample_run(), profile())
        self.assertEqual(facts["decode_rate_tok_s"], 0.0)
        self.assertFalse(facts["decode_rate_available"])
        self.assertTrue(facts_from_run(fixtures.recorded_run(), profile())["decode_rate_available"])

    def test_per_request_rate_is_the_token_weighted_aggregate(self):
        """What this pins, and what it cannot prove.

        The per-request series are built from the same recorded totals the
        counters carry, so tokens/rounds equals committed/(committed-accepted)
        by construction: this test pins the token-weighted aggregation, the
        steady-window handling and that a per-request *mean* would not pass. It
        says nothing about the engine's own two producers agreeing; only the
        live half of A2 in tests/test_acceptance.py can speak to that.
        """
        facts = facts_from_run(fixtures.recorded_run(), profile())
        self.assertAlmostEqual(facts["engine_request_rate_tok_s"], 109.0954, delta=0.01)
        self.assertEqual(facts["engine_request_count"], 18)
        # Section 4.1: the per-request rounds are the measured cross-check of
        # the factor derived from the counters.
        self.assertAlmostEqual(facts["engine_request_tokens_per_round"],
                               facts["spec_tokens_per_forward"], delta=0.01)

    def test_an_unavailable_ratio_does_not_buy_rank(self):
        """A3's fix, one layer down: the 0.0 sentinel must not pay headroom.

        The rule still fires -- the power ratio is measured and the Basis line
        says so -- but a run that produced no rate must not be paid the ranking's
        maximum headroom bonus for a ratio it cannot support. A run whose ratio
        is real keeps the score it had.
        """
        facts = facts_from_run(fixtures.no_rate_run(), profile())
        self.assertEqual(facts["decode_rate_tok_s"], 0.0)
        self.assertFalse(facts["decode_rate_available"])
        self.assertEqual(facts["objective_ratio"], 0.0)
        self.assertFalse(facts["objective_ratio_available"])

        ranked = hypotheses_from_run(fixtures.no_rate_run(), profile(), rules())
        self.assertEqual([h.rules[0] for h in ranked], ["sm89.power-cap-limit"])
        self.assertIs(ranked[0].confidence, Quality.MEASURED)
        self.assertEqual(ranked[0].rank_score, 3.0)  # the confidence weight alone

        real_facts = facts_from_run(fixtures.treatment_run(), profile())
        self.assertTrue(real_facts["objective_ratio_available"])
        real = hypotheses_from_run(fixtures.treatment_run(), profile(), rules())[0]
        self.assertAlmostEqual(real.rank_score, 3.0 + (1.0 - real_facts["objective_ratio"]), places=6)
        self.assertGreater(real.rank_score, ranked[0].rank_score)

    def test_rank_is_deterministic_across_rule_order(self):
        run = fixtures.two_rules_run()
        base = rules()
        expected = ["sm89.power-cap-limit", "sm89.thermal-throttle"]
        self.assertEqual([h.rules[0] for h in hypotheses_from_run(run, profile(), base)], expected)
        for shuffled in (list(reversed(base)), base[1:] + base[:1]):
            self.assertEqual([h.rules[0] for h in hypotheses_from_run(run, profile(), shuffled)], expected)
        self.assertEqual([h.rules[0] for h in rank(hypotheses_from_run(run, profile(), base))], expected)


if __name__ == "__main__":
    unittest.main()
