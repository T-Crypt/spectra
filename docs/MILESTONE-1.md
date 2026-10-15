# Milestone 1 implementation plan

Goal, a walking skeleton that observes a live engine, stores a raw run, and regenerates a correlated report from that stored run alone.

This plan turns the milestone described in `docs/DESIGN.md` into an ordered set of commits. Each commit ends in a state that runs and is checked. Each commit is a future PR.

C1-C12 are implemented and green. `python -m unittest discover -s tests` reports 74 tests OK: the package scaffold, the domain types in `adascope/model.py`, the append-only run store in `adascope/store.py`, both adapters, `observe`, the reference model, the rule engine, analysis, the report, and the acceptance and eval tests.

## Definition of done

The milestone is done when all of these hold on the test machine.

1. `spectra observe` writes a `Run` to disk from live NVML and engine data.
2. `spectra report` renders that `Run` to text, reading no live source.
3. Rendering the same stored `Run` twice is byte-identical.
4. The decode rate Spectra derives from engine counters matches the engine's own per-request decode rate within one percent.
5. The induced-bottleneck eval ranks the seeded cause first for at least the power-cap case.

## Out of scope

Applying configuration changes. The controlled runner. Kernel traces from Nsight. The local-model assistance layer. A web UI. Anything beyond one reference model (memory-bound dense decode) and three rules.

## Confirmed integration facts

These are measured on the test machine and the plan depends on them.

| Fact | Value | Source |
| --- | --- | --- |
| GPU | NVIDIA RTX 4090, sm_89 | `nvidia-smi` |
| VRAM | 24564 MiB | `nvidia-smi` |
| Power limit, default, max | 450 W, 450 W, 480 W | `nvidia-smi -q` |
| Max clocks | SM 3135 MHz, memory 10501 MHz | `nvidia-smi -q` |
| Driver, CUDA UMD | 615.71.09, 13.4 | `nvidia-smi` |
| Engine endpoint | `http://127.0.0.1:5804` | `curl /health` returned `{"status":"ok"}` |
| Model | `NInfer-Qwen3.8-27B`, context 262144 | `curl /v1/models` |
| Artifact bytes | 18210531328 (16.96 GiB) | `stat` |
| Engine counters | `llamacpp:tokens_predicted_total`, `llamacpp:tokens_predicted_seconds_total`, `ninfer:draft_tokens_total`, `ninfer:draft_accepted_tokens_total` | `curl /metrics` |
| Observed cumulative decode rate | 65329 / 598.824419 = 109.1 tok/s | `curl /metrics` |
| Observed speculative acceptance | 43693 / 65850 = 66.4% | `curl /metrics` |

Driver note, 2026-10-15: `nvidia-smi` now reports 615.78.08 for the driver, with CUDA UMD 13.4 unchanged. The 615.71.09 above is the value measured when this table was written. Nothing else in the table was re-measured.
| Memory ceiling, pre-spec | 1008e9 / 18210531328 = 55.4 tok/s | derived |
| Nsight | not installed | `command -v ncu nsys` |
| NVML library | `libnvidia-ml.so.1` loads | `ctypes` probe |

The observed 109.1 tok/s sits above the 55.4 tok/s ceiling because speculative decoding produces more than one token per weight read. The ratio, about 1.97, is the speculative factor the reference model must carry. This is the first real thing the milestone has to get right.

## Type spec for Phase 1

Full model is in `docs/DESIGN.md`. This is the subset Phase 1 stores or computes, with fields frozen at commit C2.

Stored on disk, in `Run`:

```
HardwareProfile
  name, arch, compute_capability
  vram_total_bytes
  mem_bandwidth_measured_gbps        # None unless a probe ran
  power_limit_w, power_default_w, power_max_w
  clock_sm_max_mhz, clock_mem_max_mhz
  driver_version, cuda_driver_version

Workload
  adapter_id, engine_id, engine_version
  model_id, artifact_path, artifact_bytes, artifact_sha256
  objective {metric, direction, target}
  constraints {latency_slo_ms, memory_budget_bytes}
  config {flag_name: value}

Series
  metric, unit, source, quality
  samples [(t_seconds, value)]

Run
  id, started_at, ended_at
  hardware, workload
  sampling {interval_ms, duration_s}
  sources [adapter_id]
  artifacts [path]
  series [Series]
```

Computed at report time, never stored in Phase 1:

```
Observation
  run_id, metric, value, unit, window, comparison, method, source_series

ReferenceModel
  workload_class, objective_unit, ceiling, limiting_resource
  derivation {formula, inputs, assumptions}, quality=derived

Hypothesis
  id, run_id, claim, mechanism, rank_score
  evidence [observation], rules [rule_id], alternatives, confidence
```

The split is deliberate. The store holds raw measurements. Analysis is a pure function of the stored run plus static profiles. That is what makes test 3 possible.

Enums. `Quality` in `{measured, derived, hypothesis}`. `ClaimKind` in `{bounded_by, starved, contended, misconfigured}`. `Direction` in `{maximize, minimize}`.

## The commit stack

Twelve commits in five stacked units. Each line is a commit. The verification column is the command that must pass before the next commit starts.

| # | Commit | Unit | Verification |
| --- | --- | --- | --- |
| C1 | `chore: scaffold package, test harness, and ignore rules` | Foundation | `python -m unittest discover` |
| C2 | `feat(model): add domain types with JSON round-trip` | Foundation | `python -m unittest tests.test_model` |
| C3 | `feat(store): add append-only run store` | Foundation | `python -m unittest tests.test_store` |
| C4 | `feat(adapters): add NVML hardware and telemetry adapter` | Observe | `python -m unittest tests.test_nvml` |
| C5 | `feat(adapters): add lmcompat engine adapter` | Observe | `python -m unittest tests.test_lmcompat` |
| C6 | `feat(cli): add observe command` | Observe | observe smoke run, then load |
| C7 | `feat(reference): add memory-bound dense decode model` | Reason | `python -m unittest tests.test_reference` |
| C8 | `feat(engine): add structured rule evaluator and sm_89 rules` | Reason | `python -m unittest tests.test_engine` |
| C9 | `feat(analyze): derive observations and rank hypotheses` | Reason | `python -m unittest tests.test_analyze` |
| C10 | `feat(report): render a stored run as text` | Report | `python -m unittest tests.test_report` |
| C11 | `test(accept): add fidelity and reproducibility tests` | Report | `python -m unittest tests.test_acceptance` |
| C12 | `test(eval): add induced-bottleneck eval` | Eval | `python tests/eval_induced_bottleneck.py` |

## Per-commit detail

### C1 `chore: scaffold package, test harness, and ignore rules`

Files. `.gitignore` (`runs/`, `__pycache__/`, `*.pyc`, `.venv/`). `pyproject.toml` with `requires-python >= 3.11`, no runtime dependencies, and a console script `spectra = adascope.cli:main`. `adascope/__init__.py`. `adascope/__main__.py` calling `cli.main`. `adascope/cli.py` with an argparse shell that dispatches to nothing yet. `tests/__init__.py`.

Why first. Every later commit imports this package and runs under this harness. Scaffold before features.

Verify. `python -m unittest discover -s tests` runs the scaffold smoke test and exits zero. `python -c "import adascope"` succeeds. Python 3.12 and later exit 5 when a discovery finds no tests, so the smoke test keeps the check meaningful.

### C2 `feat(model): add domain types with JSON round-trip`

Files. `adascope/model.py`, `tests/test_model.py`.

Interface. `@dataclass` types above. `to_dict(obj)` and `from_dict(cls, d)` for every type, plus `Run.to_json()` and `Run.from_json(text)`. Enums serialize by name. Tuples serialize as two-element lists.

Test. Build one fully populated `Run` with literal field values, serialize, deserialize, assert the result equals the original. Assert a Series sample tuple survives as a tuple. This is behavior, not implementation.

### C3 `feat(store): add append-only run store`

Files. `adascope/store.py`, `tests/test_store.py`.

Interface. `save_run(run, root) -> Path`, `load_run(path) -> Run`, `list_runs(root) -> list[Path]`. Filename is `<run_id>.json`.

Atomicity. Write to `<run_id>.json.tmp`, `fsync`, then `os.replace`. A crash leaves a temp file that `list_runs` ignores. Saving the same run twice converges to the same file with the same bytes.

Test. Save then load equals the original. Save twice, assert one file and identical bytes. Write a junk `.tmp` file, assert `list_runs` ignores it.

### C4 `feat(adapters): add NVML hardware and telemetry adapter`

Files. `adascope/adapters/__init__.py`, `adascope/adapters/nvml.py`, `tests/test_nvml.py`.

Interface. `class Nvml: def discover(device_index=0) -> HardwareProfile`, `def sample(device_index=0) -> dict[str, float | int | bool]`. ctypes against `libnvidia-ml.so.1`. Call `nvmlInit_v2`, then `nvmlDeviceGetName`, `nvmlDeviceGetMemoryInfo`, `nvmlDeviceGetPowerManagementLimit` and `...DefaultLimit` and `...LimitConstraints`, `nvmlDeviceGetMaxClockInfo` for SM and memory, `nvmlDeviceGetTemperature`, `nvmlDeviceGetUtilizationRates`, `nvmlDeviceGetClockInfo` for current clocks, `nvmlDeviceGetCurrentClocksThrottleReasons`, `nvmlDeviceGetCudaComputeCapability`, `nvmlSystemGetDriverVersion`, `nvmlSystemGetCudaDriverVersion`. Free strings with `nvmlDeviceGetName` returning a fixed buffer for this ctypes binding.

Boundary. This module is one of the only two places that touch foreign formats. Parse NVML values into domain units (watts, MHz, bytes, a boolean per throttle bit) here. Everything downstream trusts the types.

Test, skipped when no GPU is present. Assert the name contains `4090`, `vram_total_bytes` is within 1% of 24564 MiB, `power_limit_w` is 450.0 within tolerance, `clock_sm_max_mhz` is 3135 within tolerance. Assert `sample()` returns the expected keys and that `throttle` decodes to named booleans. Cross-check one live value against `nvidia-smi --query-gpu=power.limit` in the same test.

### C5 `feat(adapters): add lmcompat engine adapter`

Files. `adascope/adapters/lmcompat.py`, `tests/test_lmcompat.py`.

Interface. `class LmCompat: def __init__(host, port)`, `def models() -> list[dict]`, `def metrics() -> dict[str, float]`, `def workload(model_id, config, artifact_path) -> Workload`. HTTP via `urllib.request` from the standard library. Parse the Prometheus text body by stripping the `llamacpp:` and `ninfer:` prefixes and returning a name to float map. Read `GET /v1/models` for the model id and context window. Config and artifact path come from the operator in Phase 1, because the server exposes no launch-config endpoint. When a JSONL path is supplied, read the `server_start` record for config instead, and read `request_done` records for per-request timings.

Test, skipped when the server is down. Against `127.0.0.1:5804`, assert `llamacpp:tokens_predicted_total` is present and non-negative, take two `/metrics` samples one second apart, assert `tokens_predicted_seconds_total` is non-decreasing. Assert `models()` returns an id containing `NInfer`.

### C6 `feat(cli): add observe command`

Files. `adascope/cli.py` extended, `adascope/observe.py`, `tests/test_cli_observe.py`.

Interface. `spectra observe --target HOST:PORT --duration 30 --hz 2 --artifact PATH --config FILE --metrics-jsonl PATH --out runs/`. Parse and validate the target at the boundary. Loop for `duration`, sample NVML at `hz`, poll `/metrics` at `hz`, accumulate two `Series` (hardware, engine) plus per-request series from JSONL when present. Build the `Run` and `save_run`.

Verify. `python -m spectra observe --target 127.0.0.1:5804 --duration 30 --hz 2 --artifact /home/tcrypt/ninfer-4090/models/qwen3_8_27b.ninfer --out runs/smoke.json`, then load the file and assert the sample count is at least `duration * hz` minus a tolerance and both series are non-empty.

### C7 `feat(reference): add memory-bound dense decode model`

Files. `adascope/reference.py`, `profiles/sm89.json`, `tests/test_reference.py`, `tests/test_reference_sm89.py`.

Interface. `dense_decode_reference(artifact_bytes, kv_bytes_per_token, context_tokens, bandwidth_gbps, spec_tokens_per_forward) -> ReferenceModel`. Pure.

Formula.

```
bytes_per_forward    = artifact_bytes + kv_bytes_per_token * context_tokens
tokens_per_forward   = spec_tokens_per_forward
ceiling_tok_per_s    = bandwidth_gbps * 1e9 / bytes_per_forward * tokens_per_forward
```

`profiles/sm89.json` holds `mem_bandwidth_spec_gbps: 1008`, `sm_count: 128`, citations to the Ada tuning guide and the RTX 4090 specifications.

Test. With `artifact_bytes = 18210531328`, `bandwidth_gbps = 1008`, `spec_tokens_per_forward = 1`, assert the ceiling is 55.4 within 0.1. Assert `quality` is `derived` and the derivation lists its inputs. A second case with `spec_tokens_per_forward = 1.97` asserts the ceiling near 109, the observed rate. This test is where the number is explained.

### C8 `feat(engine): add structured rule evaluator and sm_89 rules`

Files. `adascope/engine.py`, `adascope/rules/sm89.json`, `tests/test_engine.py`.

Interface. `evaluate(predicate, facts) -> bool` over a tiny expression language. `{"all": [...]}`, `{"any": [...]}`, `{"not": ...}`, comparison nodes `{"gt": [field, value]}`, `{"lt": ...}`, `{"ge": ...}`, `{"le": ...}`, `{"eq": ...}`, and `{"bool": field}`. No `eval`. `fires(rule, facts)` calls the evaluator on `rule.applies_when`.

The three rules.

```
sm89.power-cap-limit
  applies_when: all(power_ratio >= 0.95, objective_ratio < 0.90)
  claim_kind: bounded_by
  claim: limited by the power cap
  confidence: measured when throttle.power_cap is true, else supported
  citation: NVML throttle reason bits; Ada boost behavior

sm89.thermal-throttle
  applies_when: all(temp_c >= 83, throttle.thermal is true)
  claim_kind: bounded_by
  claim: limited by temperature
  confidence: measured
  citation: NVML throttle reason bits

sm89.decode-near-bandwidth-roof
  applies_when: objective_ratio >= 0.90
  claim_kind: bounded_by
  claim: memory bandwidth is the limit; further tuning has little headroom
  confidence: derived
  citation: 1008 GB/s documented memory bandwidth
```

`facts` is a flat dict produced in C9, for example `power_ratio`, `objective_ratio`, `temp_c`, `throttle.power_cap`, `throttle.thermal`. Keeping facts flat and rules as data means a new architecture is a new JSON file.

Test. Feed synthetic fact dicts and assert the exact set of fired rule ids. One case per rule firing, one case firing none, one case where two rules tie.

### C9 `feat(analyze): derive observations and rank hypotheses`

Files. `adascope/analyze.py`, `tests/test_analyze.py`.

Interface. `facts_from_run(run, profile) -> dict`, `observations_from_run(run) -> list[Observation]`, `references_from_run(run, profile) -> list[ReferenceModel]`, `hypotheses_from_run(run, profile, rules) -> list[Hypothesis]`, `rank(hypotheses) -> list[Hypothesis]`. All pure.

Steady window. Drop the first 10 percent of samples as warmup. `power_ratio = mean(power_draw) / power_limit`. `objective_ratio = decode_rate / reference.ceiling`. `temp_c = max(temperature)`. Throttle booleans come from the OR over the window.

Rank score. `rank_score = w1 * confidence_weight + w2 * potential_benefit - w3 * experiment_cost`, with weights as named constants and a documented default. Ties break by rule id for determinism.

Test. From a fixture `Run` with crafted series, assert the derived `objective_ratio` and `power_ratio` equal literal expected values, assert the reference ceiling matches, and assert the ranked rule id order is exactly the expected list.

### C10 `feat(report): render a stored run as text`

Files. `adascope/report.py`, `tests/test_report.py`.

Interface. `render(run, profile, rules) -> str`, pure. Runs C9 then formats the report in the shape shown in the README, with each number labeled measured, derived, or hypothesis.

Test. Load a fixture `Run`, render twice, assert byte equality. Assert the output contains the ceiling line and each hypothesis with its label. A golden file `tests/fixtures/report.golden.txt` pins the format.

### C11 `test(accept): add fidelity and reproducibility tests`

Files. `tests/test_acceptance.py`, fixtures under `tests/fixtures/`.

Reproducibility. Render a fixture run twice, byte-equal.

Fidelity. From a run that includes both `/metrics` samples and JSONL `request_done` records, compute the decode rate from counter deltas, compute it from per-request `predicted_per_second` weighted by predicted tokens, assert they agree within one percent. This compares two independent methods for the same quantity, so agreement is real evidence and not circular.

### C12 `test(eval): add induced-bottleneck eval`

Files. `tests/eval_induced_bottleneck.py`, `docs/EVAL.md`.

The eval. Optionally set `nvidia-smi -pl 150`, run `observe` against a fixed decode load, analyze, and assert the top-ranked hypothesis id is `sm89.power-cap-limit`. Restore the power limit in a `finally`. Skip with a clear message when the process lacks permission to set the power limit.

Report a hit rate across the cases run. This script is the milestone's own success metric.

## Test strategy

`unittest` from the standard library, run with `python -m unittest discover -s tests`. Zero runtime dependencies. Hardware and network tests are guarded so the suite passes on a machine with no GPU and no server. Functional tests use fixtures, not live calls.

## Risks

1. **ctypes NVML struct and string handling.** The highest-risk code. `nvmlDeviceGetName` writes a fixed-size char buffer, and several calls pass a `c_uint` by reference. Take it slowly and test against `nvidia-smi` in the same test.
2. **The engine exposes no launch-config endpoint.** Phase 1 takes config from the operator. If `--request-log-jsonl` is enabled, prefer the `server_start` record. Confirm which path you want before C5.
3. **Speculative factor in the reference model.** `spec_tokens_per_forward` is measured from counters, not assumed. If the acceptance ratio is unstable, the ceiling is unstable. The fidelity test in C11 is what keeps this honest.
4. **GPU exclusivity for the eval.** The live server holds about 23 of 24 GB. The eval in C12 needs a controlled load and possibly a restart. It is skipped, not faked, when the environment is wrong.

## Execution checkpoints

The throughput checkpoint, per the Feature playbook.

* **Blocking first steps.** C1, C2, C3. The package, the frozen types, and the store block everything. One worker, serial.
* **Independent workstreams.** After C3, C4 (NVML), C5 (lmcompat), C7 (reference), and C8 (rule evaluator) touch disjoint files and can run in parallel.
* **Shared mutable state.** None. The contract is the C2 schema, frozen. C4 and C5 each fill their own adapter. No two workers write the same file.
* **Smallest safe decomposition.** C6 (observe CLI) integrates C3, C4, and C5, so it serializes after them. C9 depends on adapter metric names, so it follows C6. C10 follows C9. C11 and C12 verify C9 and C10 and run last.

Re-run this checkpoint at each stack boundary. C1 to C3 are one worker. C4, C5, C7, C8 fan out. C6, C9, C10, C11, C12 serialize.
