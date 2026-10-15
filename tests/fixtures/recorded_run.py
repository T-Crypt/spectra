"""Fixture runs for the analysis tests.

Every number here is either a recorded measurement or arithmetic on one, and
the module says which. No GPU and no server is involved.

The recorded run carries the counters recorded in docs/MILESTONE-1.md:
tokens_predicted_total 65329, tokens_predicted_seconds_total 598.824419,
draft_tokens_total 65850, draft_accepted_tokens_total 43693, against the
artifact the counters were measured with, 18210531328 bytes. The live engine
loads a later artifact of 18210749936 bytes, so the artifact byte count here
stays at the recorded value on purpose.
"""

from __future__ import annotations

from adascope.model import HardwareProfile, Quality, Run, Series, Workload
from tests.fixtures import machine

LIMIT_W = 450.0
BANDWIDTH_GBPS = 1008.0
PRE_SPEC_CEILING = BANDWIDTH_GBPS * 1e9 / machine.RECORDED_ARTIFACT_BYTES

# docs/MILESTONE-1.md, measured on the engine at 127.0.0.1:5804.
RECORDED_TOKENS = 65329.0
RECORDED_DECODE_SECONDS = 598.824419
RECORDED_DRAFTED = 65850.0
RECORDED_ACCEPTED = 43693.0
RECORDED_RATE = RECORDED_TOKENS / RECORDED_DECODE_SECONDS
RECORDED_ROUNDS = RECORDED_TOKENS - RECORDED_ACCEPTED


def hardware() -> HardwareProfile:
    return HardwareProfile(
        name="NVIDIA GeForce RTX 4090",
        arch="sm_89",
        compute_capability="8.9",
        vram_total_bytes=24564 * 1024 * 1024,
        power_limit_w=LIMIT_W,
        power_default_w=LIMIT_W,
        power_max_w=480.0,
        clock_sm_max_mhz=3135,
        clock_mem_max_mhz=10501,
        driver_version="615.78.08",
        cuda_driver_version="13.4",
    )


def workload(artifact_bytes: int = machine.RECORDED_ARTIFACT_BYTES) -> Workload:
    return Workload(
        adapter_id="lmcompat",
        engine_id="ninfer",
        engine_version=None,
        model_id="NInfer-Qwen3.8-27B",
        artifact_path=machine.RECORDED_ARTIFACT_PATH,
        artifact_bytes=artifact_bytes,
        objective={"metric": "decode_tokens_per_second", "direction": "maximize", "target": None},
        constraints={"latency_slo_ms": None, "memory_budget_bytes": None},
        config={},
    )


def _run(run_id: str, series: list[Series], sources: list[str]) -> Run:
    return Run(
        id=run_id,
        started_at="2026-10-15T12:00:00Z",
        ended_at="2026-10-15T12:10:00Z",
        hardware=hardware(),
        workload=workload(),
        sampling={"interval_ms": 500, "duration_s": 600.0},
        sources=sources,
        artifacts=[],
        series=series,
    )


def _flat(metric: str, value: float, unit: str, source: str, count: int = 10,
          span_s: float = 600.0) -> Series:
    step = span_s / max(1, count - 1)
    samples = [(i * step, value) for i in range(count)]
    return Series(metric=metric, unit=unit, source=source, quality=Quality.MEASURED, samples=samples)


def _counter(metric: str, value: float, unit: str, source: str, span_s: float = 600.0) -> Series:
    return Series(metric=metric, unit=unit, source=source, quality=Quality.MEASURED,
                  samples=[(0.0, 0.0), (span_s, value)])


def _per_request_series(total_tokens: float, total_seconds: float, rounds: float,
                        count: int = 20, span_s: float = 600.0) -> list[Series]:
    """Cumulative per-request series over the window.

    The opening requests carry nothing and fall inside the first 10 percent the
    steady rule drops, exactly as the counters' opening samples do. What is
    left sums to ``total_tokens`` and ``total_seconds``, so the token-weighted
    aggregate is the same number the counters give.

    That equality is by construction, not a finding: it is what makes the
    per-request assertions in tests/test_acceptance.py and tests/test_analyze.py
    pins on the aggregation and the window handling rather than evidence about
    the engine. Only a live run under load can say anything about the engine.
    """
    warmup = count // 10 + 1
    steps = count - warmup
    step = span_s / count
    tokens = seconds = round_ = 0.0
    series = {"request_decode_tokens": [], "request_decode_seconds": [], "request_decode_rounds": []}
    for i in range(count):
        if i >= warmup:
            tokens += total_tokens / steps
            seconds += total_seconds / steps
            round_ += rounds / steps
        series["request_decode_tokens"].append((i * step, tokens))
        series["request_decode_seconds"].append((i * step, seconds))
        series["request_decode_rounds"].append((i * step, round_))
    return [
        Series(metric="request_decode_tokens", unit="count", source="lmcompat:jsonl",
               quality=Quality.MEASURED, samples=series["request_decode_tokens"]),
        Series(metric="request_decode_seconds", unit="s", source="lmcompat:jsonl",
               quality=Quality.MEASURED, samples=series["request_decode_seconds"]),
        Series(metric="request_decode_rounds", unit="count", source="lmcompat:jsonl",
               quality=Quality.MEASURED, samples=series["request_decode_rounds"]),
    ]


def crafted_run() -> Run:
    """The literal-value fixture: 445 W against a 450 W limit, 63 C, a 47.5 tok/s rate."""
    return _run(
        "fixture-crafted",
        [
            Series("power_draw_w", "W", "nvml", Quality.MEASURED,
                   [(0.0, 400.0)] + [(float(i), 445.0) for i in range(1, 10)]),
            Series("temp_c", "C", "nvml", Quality.MEASURED,
                   [(0.0, 60.0), (1.0, 61.0), (2.0, 61.0), (3.0, 62.0), (4.0, 62.0),
                    (5.0, 62.0), (6.0, 63.0), (7.0, 63.0), (8.0, 63.0), (9.0, 63.0)]),
            _counter("tokens_predicted_total", 380.0, "count", "lmcompat", span_s=4.0),
            _counter("tokens_predicted_seconds_total", 8.0, "s", "lmcompat", span_s=4.0),
            Series("throttle.sw_power_cap", "", "nvml", Quality.MEASURED, [(0.0, 1.0), (4.0, 1.0)]),
        ],
        ["nvml", "lmcompat"],
    )


def recorded_run(with_requests: bool = True) -> Run:
    """The counter values recorded in docs/MILESTONE-1.md, with no GPU."""
    series = [
        _flat("power_draw_w", 300.0, "W", "nvml"),
        _flat("temp_c", 70.0, "C", "nvml"),
        _counter("tokens_predicted_total", RECORDED_TOKENS, "count", "lmcompat"),
        _counter("tokens_predicted_seconds_total", RECORDED_DECODE_SECONDS, "s", "lmcompat"),
        _counter("draft_tokens_total", RECORDED_DRAFTED, "count", "lmcompat"),
        _counter("draft_accepted_tokens_total", RECORDED_ACCEPTED, "count", "lmcompat"),
        _flat("throttle.sw_power_cap", 0.0, "", "nvml"),
        _flat("throttle.sw_thermal_slowdown", 0.0, "", "nvml"),
        _flat("throttle.hw_thermal_slowdown", 0.0, "", "nvml"),
    ]
    sources = ["nvml", "lmcompat"]
    if with_requests:
        series.extend(_per_request_series(RECORDED_TOKENS, RECORDED_DECODE_SECONDS, RECORDED_ROUNDS))
        sources.append("lmcompat:jsonl")
    return _run("fixture-recorded", series, sources)


def treatment_run() -> Run:
    """Power cap seeded: 441 W of 450 W, throttle bit set, 0.70 of the ceiling."""
    ceiling = PRE_SPEC_CEILING
    rate = 0.7 * ceiling
    span = 20.0
    return _run(
        "fixture-treatment",
        [
            _flat("power_draw_w", 441.0, "W", "nvml", count=10, span_s=span),
            _flat("temp_c", 70.0, "C", "nvml", count=10, span_s=span),
            _counter("tokens_predicted_total", rate * span, "count", "lmcompat", span_s=span),
            _counter("tokens_predicted_seconds_total", span, "s", "lmcompat", span_s=span),
            _flat("throttle.sw_power_cap", 1.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.sw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.hw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
        ],
        ["nvml", "lmcompat"],
    )


def inconsistent_run() -> Run:
    """60 tok/s with no draft counters: the run beats its own derived ceiling."""
    span = 20.0
    return _run(
        "fixture-inconsistent",
        [
            _flat("power_draw_w", 200.0, "W", "nvml", count=10, span_s=span),
            _flat("temp_c", 60.0, "C", "nvml", count=10, span_s=span),
            _counter("tokens_predicted_total", 60.0 * span, "count", "lmcompat", span_s=span),
            _counter("tokens_predicted_seconds_total", span, "s", "lmcompat", span_s=span),
        ],
        ["nvml", "lmcompat"],
    )


def roof_run() -> Run:
    """0.95 of the pre-speculation ceiling: the roof rule's own regime.

    No draft counters, so the model derives the ceiling at factor 1.0, and the
    rate lands just under the ceiling where ``sm89.decode-near-bandwidth-roof``
    fires. Power stays at 0.44 of the limit and temperature at 60 C, so the
    other two rules stay quiet. This is the only fixture that exercises the
    roof rule's evidence.
    """
    span = 20.0
    rate = 0.95 * PRE_SPEC_CEILING
    return _run(
        "fixture-roof",
        [
            _flat("power_draw_w", 200.0, "W", "nvml", count=10, span_s=span),
            _flat("temp_c", 60.0, "C", "nvml", count=10, span_s=span),
            _counter("tokens_predicted_total", rate * span, "count", "lmcompat", span_s=span),
            _counter("tokens_predicted_seconds_total", span, "s", "lmcompat", span_s=span),
            _flat("throttle.sw_power_cap", 0.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.sw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.hw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
        ],
        ["nvml", "lmcompat"],
    )


def one_sample_run() -> Run:
    """Counter series with a single sample each: no delta, so no rate.

    Reachable live with ``observe --duration 0.1 --hz 2``, where the sampling
    loop takes one sample. The facts keep the 0.0 sentinel, and the report must
    print the rate as unavailable rather than present the sentinel as a
    measurement.
    """
    return _run(
        "fixture-one-sample",
        [
            _flat("power_draw_w", 200.0, "W", "nvml", count=10, span_s=20.0),
            _flat("temp_c", 60.0, "C", "nvml", count=10, span_s=20.0),
            Series("tokens_predicted_total", "count", "lmcompat", Quality.MEASURED, [(0.0, 500.0)]),
            Series("tokens_predicted_seconds_total", "s", "lmcompat", Quality.MEASURED, [(0.0, 10.0)]),
        ],
        ["nvml", "lmcompat"],
    )


def no_rate_run() -> Run:
    """The cap bit set with no counter series at all: no rate, so no ratio.

    ``objective_ratio`` is the 0.0 sentinel here because the run produced no
    decode rate, and the power-cap rule's ``objective_ratio < 0.9`` conjunct is
    satisfied by that 0.0. The claim itself rests on the measured power ratio,
    but the sentinel must not also pay the ranking's maximum headroom bonus.
    """
    span = 20.0
    return _run(
        "fixture-no-rate",
        [
            _flat("power_draw_w", 445.0, "W", "nvml", count=10, span_s=span),
            _flat("temp_c", 62.0, "C", "nvml", count=10, span_s=span),
            _flat("throttle.sw_power_cap", 1.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.sw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.hw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
        ],
        ["nvml"],
    )


def two_rules_run() -> Run:
    """Power cap and thermal throttle both fire, on a 3.3/3.3 tie."""
    span = 20.0
    rate = 0.7 * PRE_SPEC_CEILING
    return _run(
        "fixture-two-rules",
        [
            _flat("power_draw_w", 445.0, "W", "nvml", count=10, span_s=span),
            _flat("temp_c", 85.0, "C", "nvml", count=10, span_s=span),
            _counter("tokens_predicted_total", rate * span, "count", "lmcompat", span_s=span),
            _counter("tokens_predicted_seconds_total", span, "s", "lmcompat", span_s=span),
            _flat("throttle.sw_power_cap", 1.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.sw_thermal_slowdown", 1.0, "", "nvml", count=10, span_s=span),
            _flat("throttle.hw_thermal_slowdown", 0.0, "", "nvml", count=10, span_s=span),
        ],
        ["nvml", "lmcompat"],
    )


def profile() -> dict:
    from adascope.reference import load_profile

    return load_profile()
