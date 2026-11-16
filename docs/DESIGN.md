# Spectra design

This document carries the vision, the data model, the implementation plan, and the working conventions. `README.md` is the short introduction. This is the reference.

C1-C12 are implemented and green: the package scaffold, the domain types in `adascope/model.py`, the append-only run store in `adascope/store.py`, both adapters, `observe`, the reference model, the rule engine, analysis, the report, and the acceptance and eval tests, with `python -m unittest discover -s tests` reporting 74 tests OK. Live stages E1 and E2 need the engine up and, for E2, a writable power limit.

## Vision

Spectra is a diagnosis and memory layer for GPU inference performance.

The end state is a tool that answers one question well. Given a workload running under-perform on a specific GPU, what is the most likely limiting resource, what evidence supports that, and what is the smallest change worth trying. Then it remembers the answer so the next person does not rediscover it.

The shape of that answer is a ranked hypothesis with linked evidence and a testable experiment. The shape of the memory is a store of Findings keyed by architecture, engine, workload class, and configuration delta.

A useful metaphor is a debugger for performance. A debugger does not change how your program runs. It observes, attributes, and lets you test a theory. Spectra is that, for the gap between what a GPU workload does and what the hardware allows.

### What the unit of value is

Not a dashboard. Dashboards show series and leave the interpretation to the reader.

The units of value are:

1. A ranked cause with evidence.
2. An experiment that can falsify that cause.
3. A stored Finding that answers a later question without a rerun.

If a proposed feature does not produce one of those, it is infrastructure and should be justified as such.

## Positioning and boundaries

Spectra is the analysis layer. It sits between measurement producers and a human decision.

| Concern | Owner | Spectra's role |
| --- | --- | --- |
| Hardware telemetry | nvidia-smi, NVML | consume |
| Engine counters and timings | the inference engine | consume |
| Kernel traces | nsys, ncu | import when present |
| Running a benchmark | the engine's own bench or a controlled runner | Phase 3, minimal |
| Storing a baseline | Spectra | own |
| Interpreting a gap | Spectra | own |
| Applying a config change | a human, via a generated diff | never auto-apply |

The test machine reinforces the boundary. Nsight Compute and Nsight Systems are not installed, and the live inference server exposes its own Prometheus counters and per-request timings. So the first real integration is telemetry plus engine counters, and kernel traces stay optional.

### Relationship to an existing engine

The first concrete workload is a local `ninfer` server. That engine already ships a benchmark tool, a Python orchestration layer, a per-model performance doc, and a Prometheus endpoint. Spectra must not rebuild any of that.

Reconnaissance of the ninfer tree located these producers, which Spectra should consume rather than duplicate:

* `GET /metrics`, Prometheus text format, in `src/serve/http_server.cpp` and `src/serve/serve_metrics.cpp`.
* A per-response `timings` block in the OpenAI-compatible reply, in `src/serve/openai_chat_response.cpp`.
* A structured JSONL stream enabled by `--request-log-jsonl`, schema v20, in `src/serve/request_log.cpp`, with per-request `timings_seconds`, host and device wait, speculative acceptance, and KV cache transfer and occupancy.
* Existing benchmark entry points under `tools/bench/` and `docs/performance/methodology.md`.

Those references come from reconnaissance, not from Spectra's own reading, and line numbers belong to the `ninfer-v3` worktree. Re-verify before depending on them.

The lesson is the design rule. Spectra consumes. The engine measures.

## Data model

This is the foundation the rest of the system is a pure function over. Get it right first. The store is append-only and serializable. Every report is a pure function of stored records.

Names below are Python-shaped because the analysis layer is Python. See [Stack](#stack).

### Environment and hardware

```
HardwareProfile          # probed at runtime, never hardcoded
  name, arch (sm_89), compute_capability
  vram_total_bytes
  mem_bandwidth_spec_gbps        # documented
  mem_bandwidth_measured_gbps    # optional, from a probe run
  pcie_link_gen, pcie_link_width
  sm_count, l2_bytes
  power_limit_w, power_default_w, power_max_w
  clock_sm_max_mhz, clock_mem_max_mhz
  driver_version, cuda_driver_version

# Phase 1 freezes a subset of these fields; see MILESTONE-1.md.
# The full list above is the target schema.
```

### Architecture profile and rules

```
ArchitectureProfile      # versioned data, one per arch
  arch, revision
  constants: mem_bandwidth_spec, host_link_bytes_per_s, sm_count, l2_bytes
  throttle_semantics: how power cap and thermal cap present on this part
  citations: [source]

Rule
  id, arch_scope
  applies_when: predicate over Observations and Reference models
  claim_kind: bounded_by | starved | contended | misconfigured
  hypothesis_template
  alternatives: [hypothesis_template]
  confidence_basis: measured | documented | hypothesis
  citation: source
```

### Workload

```
Workload
  adapter_id                  # e.g. "lmcompat"
  engine_id, engine_version
  model_id, artifact_path, artifact_bytes, artifact_sha256
  objective: metric + direction + target      # e.g. decode tokens/sec, maximize
  constraints: [latency_slo_ms, memory_budget_bytes]
  config: {flag_name: value}                   # the full launch configuration
```

Configuration is stored whole, not summarized. A baseline that cannot be relaunched is not a baseline.

### Run, Series, Observation

```
Run
  id, started_at, ended_at
  hardware: HardwareProfile
  workload: Workload
  sampling: {interval_ms, duration_s}
  sources: [adapter_id]
  artifacts: [jsonl_path, log_path, ppm_or_other]
  series: [Series]

Series
  run_id, metric, unit, source, quality: measured | derived
  samples: [(t_seconds, value)]

Observation
  run_id, metric, value, unit, window: (t0, t1) | "steady"
  comparison: against Reference | against Run
  method: how value was derived
  source_series: [series_ref]
```

### Reference model

This is the piece the first README lacked. Without it, "bottleneck" has no meaning.

```
ReferenceModel
  workload_class            # e.g. "dense-decode"
  objective_unit            # tokens/sec
  ceiling                   # derived upper bound
  limiting_resource         # memory_bandwidth | compute | host_link | power
  derivation: {formula, inputs, assumptions}
  quality: derived
```

Worked derivation for memory-bound dense decode, model-derived and labeled as such:

```
weights_bytes              = artifact_bytes
bytes_per_forward          = weights_bytes + kv_read_bytes(context)
tokens_per_forward         = committed_tokens / decode_rounds
ceiling_tokens_per_sec     = (mem_bandwidth_measured / bytes_per_forward)
                             * tokens_per_forward
```

On the test machine, `weights_bytes = 17 GB` and the documented bandwidth is 1008 GB/s, so the memory-bound pre-speculation ceiling is about 59 tokens/sec. The artifact size is measured. The bandwidth is documented. The ceiling is derived. None of it is a benchmark result.

The `tokens_per_forward` term is exact algebra, not an assumption. Every decode round commits `1 + accepted_i` tokens, so over a window `committed = rounds + accepted` and the factor is `committed / (committed - accepted)`. The engine's counters carry committed and accepted directly, and an engine that publishes a rounds counter (llama.cpp's `spec_decode_num_drafts_total`) substitutes `committed / rounds` for the subtraction. Two numbers this project once carried are both wrong, and the recorded run is what settled it (docs/EVAL.md, E0, resolved 2026-11-16): `1.97` was the rate back-solved from the pre-speculation ceiling, and `1.6635` (`1 + accepted/drafted`) treats drafted tokens as rounds, which holds only for one draft per round. The recorded run gives `65329 / (65329 - 43693) = 3.0195`, a ceiling of 167.13 tok/s, and an objective ratio of 0.6527.

The model's limits. The ceiling covers dense decode only; the per-forward byte cost counts weights alone, so `kv_read_bytes` is zero in Phase 1 and a long-context run reads below a ceiling that did not price the KV read. Power, clock, compute, and host-side cost are not modeled: a capped card can read the weights at full bandwidth and still lose tokens. The token counters are assumed stable inside the window, which A6 in docs/EVAL.md checks. When the observed rate exceeds the derived ceiling (objective ratio above 1.0), the model under-predicts this run; the report says so, and the near-roof rule does not fire. A ratio above 1.0 is a model defect to fix, not a performance finding.

### Hypothesis, Experiment, Finding

```
Hypothesis
  id, run_id
  claim: limiting_resource + mechanism
  rank_score: f(confidence, potential_benefit, experiment_cost)
  evidence: [observation_id]
  rules: [rule_id]
  alternatives: [Hypothesis]
  confidence: measured | supported | hypothesis

Experiment
  id, hypothesis_id
  baseline_run_id
  variable: one config key
  treatment_value, baseline_value
  success_criteria: {metric, direction, threshold}
  rollback: {variable, baseline_value}
  status: planned | approved | running | done | aborted

Finding
  id, hypothesis_id, experiment_id
  verdict: confirmed | rejected | inconclusive
  delta: {metric, baseline, treatment, unit, n_runs, spread}
  notes, artifacts: [run_id]
```

`Finding` is the persisted unit of knowledge. The library is a query over Findings grouped by `(arch, engine_id, workload_class, variable, direction)`.

## The architecture-aware rule engine

The engine is a small set of pure functions.

```
observations, reference, hardware -> [Hypothesis]
```

Each `Rule` is data. A rule fires when its predicate holds over the observations and the gap to the reference. The rule contributes a candidate hypothesis and a confidence basis. Ranking is a separate pure function so it can be tuned without touching rules.

The rules encode what is true for an architecture. Two examples for sm_89.

```
Rule sm89.power-cap-limit
  applies_when: power_draw near power_limit for > 20% of the steady window
                AND objective < reference ceiling
  claim_kind: bounded_by
  claim: limited by power cap, not by thermal
  alternatives: [thermal, memory_bandwidth]
  confidence_basis: measured (NVML throttle reasons)
  citation: NVML throttle reason bits; Ada boost behavior

Rule sm89.decode-near-bandwidth-roof
  applies_when: decode throughput within 10% of the memory ceiling
  claim_kind: bounded_by
  claim: memory bandwidth is the limit; further tuning has little headroom
  confidence_basis: derived
  citation: 1008 GB/s documented memory bandwidth
```

The rules matter because they are the only place architecture knowledge lives. Adding a new architecture means adding a profile and a rule set. It must never touch the core.

## Measurement adapters

Adapters are the only boundary with the outside world. They parse foreign formats into the domain types above. They are thin.

```
Adapter (protocol)
  discover()  -> HardwareProfile, Workload
  sample(dt)  -> [Series point]
  events()    -> [raw records]

lmcompat(Adapter)
  reads GET /metrics
  reads the per-response timings block
  optionally tails the engine JSONL
  never invents metrics the engine does not emit

nvml(Adapter)
  reads power, clocks, temperature, vram, utilization, throttle reasons

nsys(Adapter) / ncu(Adapter)
  Phase 3+, optional, import only
```

`ninfer` is an instance of `lmcompat`, not a special case in the core.

Engine name table. The analyser reads a fixed set of canonical series names (`tokens_predicted_total`, `tokens_predicted_seconds_total`, `draft_tokens_total`, `draft_accepted_tokens_total`, `draft_rounds_total`). Each engine writes its own names, and the table in `adascope/adapters/engines.py` maps a given engine's native names onto the canonical ones. A name the table does not know passes through unchanged, prefix stripped, so a run records what the engine emitted. `observe` detects the engine from one `/metrics` fetch (the `vllm:` prefix, the `n_decode_total` counter, or a bare `draft_tokens_total` counter) and takes `--engine` to force a table. An engine outside the table degrades honestly: vLLM publishes `generation_tokens_total` but no decode-seconds counter, so a vLLM run takes its decode rate from the wall-window fallback in the analyser, and with no draft counters the speculative factor stays at the no-speculation default.

## Milestone 1. The walking skeleton

The goal is the smallest end-to-end slice that produces a real report from real data, with a reproducibility guarantee.

Scope, deliberately narrow:

* One adapter for NVML.
* One adapter for `lmcompat` HTTP, reading `/metrics` and the per-response `timings`.
* One ReferenceModel, memory-bound dense decode.
* Three rules.
* A store that writes one `Run` to disk.
* A report that reads only the stored `Run`.

Not in scope for milestone 1: applying changes, the controlled runner, kernel traces, the AI layer, end-to-end automation of the engine.

CLI:

```
spectra observe --target 127.0.0.1:5804 --duration 120 --hz 2 --out runs/<id>.json
spectra bench   --target 127.0.0.1:5804 --duration 120 --hz 2 --prompt-words 256 --completion-tokens 256 --concurrency 1
spectra report runs/<id>.json
```

`bench` is `observe` plus the first-party driver in `adascope/bench.py`: it keeps the configured concurrency of greedy completions in flight for the whole window and records the workload in the run. The declared parameters go into `workload.config.driver`; the completed and failed counts are measured series (`driver_requests_completed`, `driver_requests_failed`), so a window in which the load did not materialise says so in the run instead of producing a quiet rate.

### Acceptance tests

These are the proof. Each is a real command with a real expected value, not a code review.

1. **Reproducibility.** `spectra report` run twice against the same stored `Run` produces byte-identical output. The report reads nothing live.
   Prove it works by running the command twice and diffing. The artifact is the diff, empty.
2. **Fidelity.** The decode tokens/sec Spectra derives from the stored samples matches the engine's own reported `predicted_per_second` for the same window within one percent. If it does not, Spectra measured something other than the work.
3. **Reference sanity.** The computed memory-bound ceiling for the 27B artifact lands in the expected band from the derivation. A ceiling far above the hardware's achievable bandwidth means the model is wrong.
4. **Attribution, the real test.** Under a deliberately induced bottleneck, the top-ranked hypothesis names the induced cause. See below.

### The induced-bottleneck eval

Correlation cannot prove causation. The honest way to prove the engine works is to induce a known cause and check that Spectra names it.

The test is cheap and needs no Nsight.

* Cap the GPU power with `nvidia-smi -pl 150` and run a fixed decode load. Expect `sm89.power-cap-limit` ranked first.
* Restore the cap and run a memory-bound load. Expect `sm89.decode-near-bandwidth-roof` first when throughput approaches the ceiling.
* Optionally force a host-bound case by increasing per-token host work.

Pass means the top hypothesis matches the seeded cause across the controlled runs. Record the hit rate. This is the project's own success metric, and it is falsifiable.

## Roadmap

Each phase ends in something demonstrable. Do not start a phase before the prior one's acceptance test passes.

### Phase 1. Observe and model

The commit-by-commit breakdown is in `docs/MILESTONE-1.md`.

Deliver: NVML and `lmcompat` adapters, the store, the decode ReferenceModel, three rules, the report, the four acceptance tests.

Exit: the induced-bottleneck eval passes on at least the power-cap and bandwidth-roof cases.

### Phase 2. Diagnose broadly

Deliver: rule set grown to cover host-bound and KV-transfer cases, using the engine's host and device wait split and KV transfer counters. Add confidence and measurement-quality indicators. Add `nsys` and `ncu` import as an optional tier.

Exit: each rule fires on a case that reproduces it, and no rule fires on a case that contradicts it.

### Phase 3. Experiment engine

Deliver: the controlled runner. It takes a `Hypothesis`, produces an `Experiment`, renders a config diff and runbook, runs the treatment after explicit approval, and stores both runs. Regression detection on the objective. Rollback is the stored baseline config.

Exit: a planned experiment round-trips to a stored `Finding`, and rollback restores the baseline exactly.

### Phase 4. Local assistance, optional

Deliver: a local model that drafts hypotheses and experiment plans from the collected evidence. Human-reviewed. Never a source of benchmark conclusions.

Exit: assistance improves the ranking hit rate on the eval, or it is cut.

The order matters. The deterministic engine and the eval come first. Assistance is a convenience over a system that already works.

## Stack

Recommended, and open to override.

* **Python 3.14, standard library only for Phase 1.** The analysis is data wrangling, arithmetic, and rendering. Python is the fastest path and the ecosystem for this work. The test machine has Python 3.14 and no numpy, and Phase 1 needs neither numpy nor a third-party dependency. Read NVML through `ctypes` against `libnvidia-ml.so.1`, which loads on the test machine.
* **Serialization: JSON or JSONL.** Human-readable, diffable, and the engine already speaks it. A columnar store is premature.
* **No native code in Phase 1.** Add a C++ or CUDA bandwidth probe only when a measured bandwidth number is worth the build cost. The engine already has a probe to reuse.
* **Rules and profiles as data files** (JSON or TOML). Not Python, not branches.

Do not add a web UI in Phase 1. The report is text.

## Repository layout

```
README.md
docs/DESIGN.md
adascope/
  cli.py            # argparse, thin shell, validation at the boundary
  model.py          # the domain types
  store.py          # append-only run and finding store
  adapters/
    nvml.py
    lmcompat.py
  reference.py      # ReferenceModel derivations
  rules/
    sm89.json
  engine.py         # pure: observations -> ranked hypotheses
  report.py         # pure: run -> text
profiles/
  sm89.json
runs/               # local, gitignored
tests/
```

## Guidance

* **Boundaries do the validation.** Parse and validate at the CLI, in each adapter, and in the store on read. Trust the domain types everywhere inside. Business logic stays pure and framework-free.
* **The report is a pure function of a stored run.** If rendering needs a live call, the model is missing a field.
* **Every number is labeled.** Measured, derived, or hypothesis. A report that cannot say which is wrong.
* **Never mutate a running process.** Spectra reads. It proposes a diff. A human applies it.
* **One variable per experiment.** If two keys change, the result is not attributable.
* **Do not duplicate a producer.** If the engine or nsys already emits it, consume it.
* **The eval is the truth.** A rule that cannot be shown to fire on a reproduction is a hypothesis in code.

## Open decisions

These are calls for the operator. Each has a default Spectra will proceed with.

1. **First win.** Default: one command that explains a single `ninfer` decode run on this 4090.
2. **Reference before evidence.** Default: no diagnosis without a ReferenceModel. Confirm this is acceptable, because it front-loads work before any pretty output.
3. **Observe or run.** Default: observe live now, run experiments only in Phase 3 against an exclusive GPU.
4. **Experiment venue.** The live server holds about 23 GB of the 24 GB on the only 4090. Default: experiments require the operator to stop and relaunch the server. Confirm, or provide a second device.
5. **Store unit.** Default: `Finding`, keyed by config delta, not raw `Run`.
6. **Engine coupling.** Default: `lmcompat` adapter with `ninfer` as one instance, no engine name in the core.
7. **Language.** Default: Python 3.14, standard library only for Phase 1.
8. **Apply changes.** Default: generate a diff and runbook, never auto-apply.
9. **Definition of done for v1.** Default: the induced-bottleneck eval passes on power-cap and bandwidth-roof.
