import json
import unittest

from adascope.model import (
    ClaimKind,
    Direction,
    HardwareProfile,
    ModelError,
    Hypothesis,
    Observation,
    Quality,
    ReferenceModel,
    Run,
    Series,
    Workload,
    run_from_json,
    run_to_json,
)


def make_run():
    hw = HardwareProfile(
        name="NVIDIA RTX 4090",
        arch="sm_89",
        compute_capability="8.9",
        vram_total_bytes=24564 * 1024 * 1024,
        mem_bandwidth_spec_gbps=1008.0,
        sm_count=128,
        power_limit_w=450.0,
        driver_version="615.71.09",
    )
    wl = Workload(
        adapter_id="lmcompat",
        engine_id="ninfer",
        engine_version="v3",
        model_id="NInfer-Qwen3.8-27B",
        artifact_bytes=18210531328,
        objective={"metric": "decode_tokens_per_sec", "direction": "maximize"},
        config={"context": 262144},
    )
    series = Series(
        metric="power_draw_w",
        unit="W",
        source="nvml",
        quality=Quality.MEASURED,
        samples=[(0.0, 320.5), (0.5, 335.0)],
    )
    return Run(
        id="test-run-1",
        started_at="2026-10-13T00:00:00Z",
        ended_at="2026-10-13T00:00:30Z",
        hardware=hw,
        workload=wl,
        sampling={"interval_ms": 500, "duration_s": 30},
        sources=["nvml", "lmcompat"],
        artifacts=["/tmp/request_log.jsonl"],
        series=[series],
    )


class ModelRoundTripTest(unittest.TestCase):
    def test_run_round_trip(self):
        run = make_run()
        text = run_to_json(run)
        back = run_from_json(text)
        self.assertEqual(back, run)

    def test_series_sample_survives_as_tuple(self):
        run = make_run()
        back = run_from_json(run_to_json(run))
        self.assertIsInstance(back.series[0].samples[0], tuple)
        self.assertEqual(back.series[0].samples[0], (0.0, 320.5))

    def test_enums_serialize_by_name(self):
        run = make_run()
        text = run_to_json(run)
        data = json.loads(text)
        self.assertEqual(data["workload"]["objective"]["direction"], "maximize")
        self.assertEqual(data["series"][0]["quality"], "measured")

    def test_observation_and_reference_round_trip(self):
        obs = Observation(
            run_id="test-run-1",
            metric="decode_tokens_per_sec",
            value=109.1,
            unit="tok/s",
            window="steady",
            comparison="against_reference",
            method="counter_delta",
            source_series=["engine:tokens_predicted_total"],
        )
        from adascope.model import from_dict
        back = from_dict(Observation, json.loads(json.dumps(obs.__dict__)))
        self.assertEqual(back.window, "steady")

        ref = ReferenceModel(
            workload_class="dense-decode",
            objective_unit="tok/s",
            ceiling=55.4,
            limiting_resource="memory_bandwidth",
            derivation={"formula": "bandwidth / bytes_per_forward"},
        )
        self.assertEqual(ref.quality, Quality.DERIVED)

    def test_claim_kind_enum(self):
        self.assertEqual(ClaimKind.BOUNDED_BY, "bounded_by")
        self.assertEqual(Direction.MAXIMIZE, "maximize")

    def test_unknown_field_raises_domain_error(self):
        # An AdaScope run file spells this field cuda_umd_version.
        payload = {
            "name": "NVIDIA GeForce RTX 4090",
            "arch": "sm_89",
            "compute_capability": "8.9",
            "vram_total_bytes": 24564 * 1024 * 1024,
            "cuda_umd_version": "13.4",
        }
        from adascope.model import from_dict
        with self.assertRaises(ModelError) as caught:
            from_dict(HardwareProfile, payload)
        self.assertIn("cuda_umd_version", str(caught.exception))
        self.assertIn("HardwareProfile", str(caught.exception))

    def test_missing_required_field_raises_domain_error(self):
        payload = {
            "name": "NVIDIA GeForce RTX 4090",
            "arch": "sm_89",
            "compute_capability": "8.9",
        }
        from adascope.model import from_dict
        with self.assertRaises(ModelError) as caught:
            from_dict(HardwareProfile, payload)
        self.assertIn("vram_total_bytes", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
