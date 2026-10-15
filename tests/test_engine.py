import json
import tempfile
import unittest
from pathlib import Path

from adascope.engine import default_rules_path, evaluate, fires, load_rules, rule_confidence
from adascope.model import Quality


def facts(**over):
    base = {
        "power_ratio": 0.5,
        "objective_ratio": 0.5,
        "temp_c": 60.0,
        "throttle.sw_power_cap": False,
        "throttle.sw_thermal_slowdown": False,
        "throttle.hw_thermal_slowdown": False,
    }
    base.update(over)
    return base


def rules_by_id():
    return {r["id"]: r for r in load_rules(default_rules_path())}


class EngineTest(unittest.TestCase):
    def test_power_cap_rule_fires(self):
        rules = rules_by_id()
        hit = facts(power_ratio=0.98, objective_ratio=0.7, **{"throttle.sw_power_cap": True})
        self.assertTrue(fires(rules["sm89.power-cap-limit"], hit))
        self.assertFalse(fires(rules["sm89.thermal-throttle"], hit))
        self.assertFalse(fires(rules["sm89.decode-near-bandwidth-roof"], hit))

    def test_thermal_rule_fires(self):
        rules = rules_by_id()
        hit = facts(temp_c=85.0, **{"throttle.sw_thermal_slowdown": True})
        self.assertTrue(fires(rules["sm89.thermal-throttle"], hit))
        self.assertFalse(fires(rules["sm89.power-cap-limit"], hit))

    def test_bandwidth_roof_rule_fires(self):
        rules = rules_by_id()
        hit = facts(objective_ratio=0.95)
        self.assertTrue(fires(rules["sm89.decode-near-bandwidth-roof"], hit))
        self.assertFalse(fires(rules["sm89.power-cap-limit"], hit))

    def test_roof_rule_does_not_fire_above_its_own_ceiling(self):
        # A9: the recorded run's own counters put objective_ratio at 1.1848.
        rules = rules_by_id()
        self.assertFalse(fires(rules["sm89.decode-near-bandwidth-roof"], facts(objective_ratio=1.1848)))

    def test_quiet_machine_fires_nothing(self):
        rules = load_rules(default_rules_path())
        self.assertEqual([r["id"] for r in rules if fires(r, facts())], [])

    def test_predicate_language_shapes(self):
        self.assertTrue(evaluate({"any": [{"bool": "a"}, {"bool": "b"}]}, {"a": False, "b": True}))
        self.assertTrue(evaluate({"not": {"bool": "a"}}, {"a": False}))
        self.assertFalse(evaluate({"gt": ["x", 1]}, {}))
        with self.assertRaises(ValueError):
            evaluate({"near": ["x", 1]}, {"x": 1})

    def test_rule_confidence_follows_the_throttle_bit(self):
        # Adversarial fixture: the bit the rule cites must be in the run, or the
        # claim is not measured. A rule must not print evidence it does not have.
        cap = rules_by_id()["sm89.power-cap-limit"]
        self.assertIs(rule_confidence(cap, facts(power_ratio=0.98, objective_ratio=0.7,
                                                **{"throttle.sw_power_cap": True})), Quality.MEASURED)
        self.assertIs(rule_confidence(cap, facts(power_ratio=0.98, objective_ratio=0.7)), Quality.DERIVED)

    def test_load_rules_rejects_a_quality_outside_the_enum(self):
        rules = json.loads(Path(default_rules_path()).read_text(encoding="utf-8"))
        rules[0]["confidence_basis"] = [{"quality": "supported"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(rules, indent=2))
            with self.assertRaises(ValueError) as caught:
                load_rules(path)
        self.assertIn("sm89.power-cap-limit", str(caught.exception))
        self.assertIn("supported", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
