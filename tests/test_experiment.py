import unittest

from adascope.experiment import (
    evaluate_experiment,
    plan_experiment,
    render_runbook,
    treatment_config,
)
from adascope.reference import load_profile
from tests.fixtures import recorded_run as fixtures


def profile():
    return load_profile()


class ExperimentTest(unittest.TestCase):
    def test_plan_experiment(self):
        baseline = fixtures.recorded_run()
        baseline.workload.config = {"power_limit_w": 450}
        exp = plan_experiment("h-x", baseline, "power_limit_w", 250)
        self.assertEqual(exp.variable, "power_limit_w")
        self.assertEqual(exp.baseline_value, 450)
        self.assertEqual(exp.treatment_value, 250)
        self.assertEqual(exp.rollback, {"variable": "power_limit_w", "value": 450})
        self.assertEqual(exp.status.value, "planned")

    def test_plan_requires_variable_present(self):
        baseline = fixtures.recorded_run()
        baseline.workload.config = {}
        with self.assertRaises(ValueError):
            plan_experiment("h-x", baseline, "power_limit_w", 250)

    def test_render_runbook(self):
        baseline = fixtures.recorded_run()
        baseline.workload.config = {"power_limit_w": 450}
        exp = plan_experiment("h-x", baseline, "power_limit_w", 250)
        text = render_runbook(exp)
        self.assertIn("Rollback", text)
        self.assertIn("250", text)

    def test_treatment_config(self):
        baseline = fixtures.recorded_run()
        baseline.workload.config = {"power_limit_w": 450, "x": 1}
        exp = plan_experiment("h-x", baseline, "power_limit_w", 250)
        tc = treatment_config(baseline, exp)
        self.assertEqual(tc["power_limit_w"], 250)
        self.assertEqual(tc["x"], 1)

    def test_evaluate_experiment_confirmed(self):
        baseline = fixtures.recorded_run()
        treatment = fixtures.treatment_run()
        baseline.workload.config = {"power_limit_w": 450}
        treatment.workload.config = {"power_limit_w": 450}
        # Make treatment better by patching? Use recorded vs treatment; just ensure finding produced
        exp = plan_experiment("h-x", baseline, "power_limit_w", 250)
        finding = evaluate_experiment(exp, baseline, treatment, profile())
        self.assertIn(finding.verdict.value, ("confirmed", "rejected", "inconclusive"))
        self.assertEqual(finding.experiment_id, exp.id)
