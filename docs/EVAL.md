# Spectra evaluation design

A falsifiable research design for Milestone 1. It states one question that a measurement could
refute, the hypotheses in play, the smallest experiment that separates them on this machine, the
pass thresholds, the code and data it needs, the tests, and the three largest uncertainties.

Every environment fact below was read or run on 2026-10-15 unless it is marked otherwise.

## (a) The primary research question

> On this RTX 4090, when exactly one resource is deliberately made limiting for a single-engine
> dense-decode workload, does Spectra's ranked output name that resource first -- in at least 4 of
> 5 repetitions of the treatment -- while the same rule stays out of the top rank in an
> unmodified control run of the same workload?

Why this question and not "does the report look right": attribution is the only claim in
Milestone 1 that can be wrong without anyone noticing. A report is reproducible or it is not. A
ceiling is arithmetic. Naming the cause is a judgement, and it is the project's own success
metric (`docs/DESIGN.md`, "The induced-bottleneck eval").

**The null result.** Failure to establish the claim is any one of:

1. The top-ranked rule id differs from the seeded cause in 2 or more of the 5 treatment
   repetitions.
2. The seeded rule also ranks first in the control, where the cause was not induced. A rule that
   always wins identifies nothing.
3. Two rules tie for first rank, so the output does not name a cause.
4. The treatment could not be applied at all (no permission, no free VRAM, engine down). This is
   a null result, not a pass, and it must be recorded as inconclusive -- see the final section.

A single framework matters here: a diagnosis that is right for the wrong reason must fail. Clause
2 and the causality gate in (d) exist for that.

## (b) Competing hypotheses for the first experiment

The first experiment is the control run: the milestone workload, one configuration, repeated.
Three explanations compete for the observed decode rate.

### H1. Bandwidth-bound

- **Supports it.** The observed decode rate lands inside the predicted band: `ceiling *
  spec_tokens_per_forward` within 10 percent, where the ceiling is derived from the artifact's
  exact byte count and 1008 GB/s. Power ratio below 0.95, temperature below 83 C, and no throttle
  bit set during the steady window. The rate falls as context grows, in the direction the
  bytes-per-forward term predicts.
- **Contradicts it.** The rate sits far below the predicted ceiling while every telemetry bound is
  slack: power ratio below 0.9, temperature below 75 C, no throttle bit, and the clocks at or near
  their maximum. A slack card cannot be the explanation for a rate that low, so the bytes-per-
  forward model or its inputs are wrong.

### H2. Power-cap-limited

- **Supports it.** Power draw sits at the configured limit through the steady window
  (`power_ratio >= 0.95`), the NVML bit `sw_power_cap` is true in that same window, and lowering
  the limit lowers the rate enough that `objective_ratio` falls below 0.9. Restoring the limit
  restores the rate.
- **Contradicts it.** `sw_power_cap` is false, or the power ratio stays below 0.9, in the window
  where the rule says the cap binds. A low rate with a slack power budget is not a power-cap
  finding, whatever else is true.

### H3. The evidence does not identify a limit (speculation or host work dominates)

- **Supports it.** The decode rate tracks the speculative acceptance ratio more closely than it
  tracks power or the derived ceiling. Two runs at the same power limit and the same context, with
  different acceptance ratios, differ in rate in the direction the model predicts. Or the engine's
  own `host_exposed_seconds` and `device_wait_exposed_seconds` for decode account for the residual
  gap.
- **Contradicts it.** The acceptance ratio varies across repetitions while the rate does not move,
  or the rate moves only with power. Either observation removes the explaining variable.

H3 is the honest default. It is what "the evidence is inconclusive" looks like when it is a real
finding rather than a missing measurement: the counter that multiplies tokens per forward pass is
not stable enough to state a ceiling.

## (c) The smallest experiment that distinguishes them

Three stages, each one independent variable at a time. Each stage states its own precondition, so
a stage that cannot run is skipped with a recorded reason rather than faked.

### E0. Model consistency. No GPU work, no server, no permissions. Runs today.

One fixture `Run` carrying the counter values already recorded in `docs/MILESTONE-1.md`:
`tokens_predicted_total` 65329, `tokens_predicted_seconds_total` 598.824419,
`draft_tokens_total` 65850, `draft_accepted_tokens_total` 43693, and the artifact's measured
18210531328 bytes. Assert the derived decode rate (109.1 tok/s), the speculative factor
(disputed at writing: about 1.663 by 1 + accepted/drafted against 1.97 by the milestone's
stated ratio; resolved 2026-11-16, see below), the pre-speculation
ceiling (55.4 tok/s) and the rendered report's byte stability.

That fixture already contains a contradiction that E0 must resolve before any later stage is
worth running. The counter-derived speculative factor is `1 + 43693/65850 = 1.6635`, which gives a
ceiling of 92.08 tok/s (1008e9 / 18210531328 * 1.6635). The measured rate is 109.1 tok/s, so
`objective_ratio` would be 1.185: the run exceeds the ceiling its own counters imply. The
milestone reaches 109.0 tok/s only by asserting a factor of 1.97, which is 109.1 divided by the
pre-speculation ceiling (55.353 tok/s) rather than measured from the draft counters. One of the
two factors is wrong, and if the counter-derived one is right, the bandwidth-roof rule fires on a
ratio above 1.0 and the diagnosis is meaningless.

What it decides: whether the arithmetic and the report hold, and which speculative factor is the
real one. It cannot separate H1, H2 and H3, and it must not be presented as if it does. It is the
fixture every later stage reuses, and it is the only stage that can run in the machine's current
state.

**Resolved, 2026-11-16.** No choice between 1.6635 and 1.97 was needed, because both are
wrong in the same way: neither counts rounds. Every decode round commits exactly
`1 + accepted_i` tokens, so over the window `committed = rounds + accepted` and the factor
is `committed / (committed - accepted)`, exact algebra with no assumption about how many
drafts a round carries. From the fixture's own counters that is
`65329 / (65329 - 43693) = 3.0195`, a ceiling of 167.13 tok/s, and an objective ratio of
0.6527, below 1.0. The model is consistent on the recorded run, and the roof rule stays
quiet. `1.6635` (1 + accepted/drafted) treats drafted tokens as rounds, which holds only
for one draft per round; `1.97` is 109.1 / 55.353, the factor implied by the rate the model
is meant to predict. The code now derives the factor this way (`adascope/analyze.py`), the
roof rule applies on `0.9 <= objective_ratio <= 1.0`, and E0 passes without a GPU or a
server in `tests/test_analyze.py::test_recorded_counters_reproduce_e0`.

### E1. Control. One variable: none. Needs the engine up and the card free.

The milestone workload, one configuration, five repetitions of 120 s at 2 Hz. No variable is
changed between repetitions. This measures spread -- of the decode rate, of the speculative
factor, of power and temperature -- and it is where H1 and H3 separate: H1 predicts the rate
inside the band with a stable factor, H3 predicts the rate follows an unstable factor.

What it decides: H1 versus H3, and whether any attribution claim is even available (see A6).

### E2. Treatment. One variable: the power limit, 450 W to 250 W. Needs write permission and the card free.

Identical to E1 except the power limit, applied with `nvidia-smi -pl 250` before the run and
restored to 450 W in a `finally` block. Five repetitions. This is the only stage that can make H2
true, and it is the stage `docs/MILESTONE-1.md` C12 describes.

What it decides: H2 versus H1, subject to the causality gate in (d): the rule must be right about
*why*, not only about which ratio was small.

**Do not run E2 before E1.** Without the control, a fired power-cap rule is indistinguishable from
a rule that fires whenever throughput is low.

### E3 (optional, Phase 2). One variable: the speculation setting.

A human relaunches the engine with speculation off, or with a different draft count. This is the
cheapest single-variable test of H3 that needs no root, and it changes the model's own input
`spec_tokens_per_forward` from measured to known. It is a launch-configuration change, so
`AGENTS.md` keeps it out of Phase 1 automation: propose the change, let a human apply it, observe.

### What can run in the machine's current state

| Condition | State on 2026-10-15 | Stages that can run |
| --- | --- | --- |
| NVML read-only telemetry | Working; AdaScope's three NVML tests passed while another process held the card | E0, and the telemetry half of any stage |
| Inference engine at `127.0.0.1:5804` | Down. `curl /health` returns nothing. `llama-swap` is up on `127.0.0.1:9090` but has no token counters | No live stage |
| Free VRAM | 24564 MiB total; 17023 MiB held by pid 1293313 (`/home/tcrypt/comfy/.venv/bin/python`); `nvidia-smi --query-gpu=memory.free` reports 7108 MiB free | The 16.96 GiB artifact cannot load. E1, E2 and E3 are blocked |
| Power-limit write | `sudo -n true` fails with "sudo: a password is required" | E2 blocked |
| Nsight Compute, Nsight Systems | Neither installed (`command -v ncu nsys` finds neither) | No counter or trace tier exists, in any state |
| Root, for `ncu` counters | Not available | The counter tier is not reachable by installing alone |

So: on this machine, today, the runnable part of the design is E0 plus the pure analysis tests.
E1 and E2 need a human to stop the ComfyUI process (and, for E2, to run one privileged command).
That is a precondition to state in plain words, not a problem to work around: a 17 GiB co-tenant
on a 24 GiB card means any measurement taken now is contended, and a contended run must be
recorded as contended or discarded.

## (d) Acceptance criteria

Thresholds a test can assert. Values marked (measured) came from running AdaScope's equivalent
test on this machine on 2026-10-15; values marked as verified inputs were computed from the
counter readings recorded in `docs/MILESTONE-1.md`. Nothing else here is taken on faith.

| ID | Criterion | Threshold | Where |
| --- | --- | --- | --- |
| A1 | Reproducibility | `render(run, ...)` twice is byte-identical; zero differing bytes | `tests/test_acceptance.py`, and `tests/test_report.py` |
| A2 | Fidelity | Absolute difference between the derived decode rate and the engine's own per-request rate is at most 1 percent of the engine's number, on the same window | `tests/test_acceptance.py` |
| A3 | Reference sanity | Pre-speculation ceiling is 55.4 tok/s within 0.1 for `artifact_bytes=18210531328` and 1008 GB/s; with `spec_tokens_per_forward=1.97` it is 109.0 within 1.0 (measured) | `tests/test_reference.py` |
| A4 | Attribution | Treatment: top-ranked rule id equals the seeded cause in at least 4 of 5 repetitions. Control: the seeded rule ranks first in 0 of 5 | `tests/eval_induced_bottleneck.py` |
| A5 | Causality gate | In the treatment's steady window the run contains `throttle.sw_power_cap` true; in the control's steady window it is false. If the bit is missing or false, no attribution is claimed | eval |
| A6 | Stability | Coefficient of variation of `spec_tokens_per_forward` across the 5 control repetitions is at most 5 percent, else the ceiling is not an identifiable quantity and the result is inconclusive | eval |
| A7 | No silent estimate | Every report line carries a measured, derived or hypothesis label; a series absent from the run is reported unavailable, never estimated | `tests/test_report.py` |
| A8 | Inconclusive is recorded | When A5 or A6 fails, or two rules tie, the eval record's verdict is `inconclusive`, and no acceptance test counts it as a pass | eval |
| A9 | Model self-consistency | `objective_ratio` computed from the run's own counters must not exceed 1.0. If it does, the report must say the reference model under-predicts and must not fire a near-roof claim. Verified inputs (resolved 2026-11-16): the recorded counters give factor 3.0195, ceiling 167.13, ratio 0.6527, consistent; a 60 tok/s run with no draft counters sits at ratio 1.084 against the 55.353 ceiling and must print the under-prediction note with no roof rule fired | `tests/test_analyze.py`, `tests/test_report.py` |

A4 and A5 pair deliberately. A4 alone can be satisfied by a rule that fires because one ratio
crossed a threshold, which is arithmetic, not diagnosis. A5 is what makes the claim causal: the
same NVML bit the rule cites must be present in the run's own data.

## (e) Data format and code needed

### Reference to the frozen C2 types

The experiment uses these types by name, exactly as frozen in `adascope/model.py`. None of them
needs a field added.

| Type | Fields the experiment uses |
| --- | --- |
| `Run` | `id`, `started_at`, `ended_at`, `sampling` (dict: `interval_ms`, `duration_s`), `sources`, `artifacts`, `series` |
| `HardwareProfile` | `name`, `arch`, `compute_capability`, `vram_total_bytes`, `power_limit_w`, `power_default_w`, `power_max_w`, `clock_sm_max_mhz`, `clock_mem_max_mhz`, `driver_version`, `cuda_driver_version`, `mem_bandwidth_spec_gbps` |
| `Workload` | `adapter_id`, `engine_id`, `model_id`, `artifact_path`, `artifact_bytes`, `objective` (dict), `constraints` (dict), `config` (dict) |
| `Series` | `metric`, `unit`, `source`, `quality`, `samples` |
| `Observation` | `metric`, `value`, `unit`, `window`, `comparison`, `method`, `source_series` |
| `ReferenceModel` | `workload_class`, `objective_unit`, `ceiling`, `limiting_resource`, `derivation`, `quality` |
| `Hypothesis` | `id`, `claim`, `mechanism`, `rank_score`, `evidence` (list of observation ids), `rules`, `alternatives`, `confidence` |
| Enums | `Quality` (measured, derived, hypothesis), `ClaimKind`, `Direction` |

Two consequences of the frozen shapes:

- `Hypothesis.evidence` holds **ids**, so the analyser must emit observation ids and the renderer
  must resolve them against the run's observations. AdaScope's analyser puts `Observation`
  objects in `evidence` and must be rewritten.
- `Run.sampling` is a dict, so `observe` must validate `interval_ms` and `duration_s` itself.
  There is no `Sampling` type to lean on.

### What is missing from Spectra

| Missing | Content needed | Blocks |
| --- | --- | --- |
| `profiles/sm89.json` | The AdaScope file's keys, read for this design: `arch` `sm_89`, `mem_bandwidth_spec_gbps` 1008, `sm_count` 128, `l2_bytes` 75497472, `pcie_link_gen` 4, `pcie_link_width` 16, `clock_sm_max_mhz` 3135, `clock_mem_max_mhz` 10501, `throttle_semantics`, `citations` | A3, every ceiling |
| `adascope/rules/sm89.json` | The three rules: `sm89.power-cap-limit` (`power_ratio >= 0.95` and `objective_ratio < 0.9`), `sm89.thermal-throttle` (`temp_c >= 83` and `throttle.sw_thermal_slowdown`), `sm89.decode-near-bandwidth-roof` (`0.9 <= objective_ratio <= 1.0`) | A4, A5 |
| `adascope/adapters/nvml.py` | ctypes binding, nine named throttle bits, `discover()` and `sample()` | E1, E2 telemetry |
| `adascope/adapters/lmcompat.py` | Prometheus parsing, `/v1/models`, JSONL reader | E1, E2 counters, A2 |
| `adascope/observe.py` | Sampling loop, `parse_target`, `save_run` | E1, E2 |
| `adascope/reference.py` | `dense_decode_reference` | A3 |
| `adascope/engine.py` | `evaluate`, `fires`, `load_rules`, `default_rules_path` | A4 |
| `adascope/analyze.py` | `facts_from_run`, `observations_from_run`, `references_from_run`, `hypotheses_from_run`, `rank` | A2, A4, A6, A7 |
| `adascope/report.py` | `render`, pure | A1, A7 |

### Metric-name contract

The analyser keys off metric names, so the adapter must emit exactly these into `Series.metric`:

| Name | Source | Used for |
| --- | --- | --- |
| `power_draw_w` | NVML | `power_ratio`, observation |
| `temp_c` | NVML | thermal rule, observation |
| `throttle.sw_power_cap`, `throttle.sw_thermal_slowdown`, `throttle.hw_thermal_slowdown` | NVML, 1.0 or 0.0 | A5, the two throttle rules |
| `tokens_predicted_total`, `tokens_predicted_seconds_total` | engine `/metrics` | derived decode rate |
| `draft_tokens_total`, `draft_accepted_tokens_total` | engine `/metrics` | speculative factor (A6) |

`tokens_predicted_total` and `tokens_predicted_seconds_total` are counters, so the derived rate is
`delta(tokens) / delta(seconds)` over the steady window. A6 watches the factor's spread, which is
why the two draft counters are in the required set rather than optional.

### Measurement source for A2 (fidelity)

The per-request rate comes from one of two producers, and they are not the same:

- the OpenAI-compatible response body's `timings` block, which carries `predicted_per_second`
  (documented; `src/serve/openai_chat_response.cpp:100` at `/home/tcrypt/wt/ninfer-v3`, HEAD
  `e85e028`);
- the JSONL request log, schema version 20 (documented; `src/serve/request_log.h:23`), where a
  `request_done` record carries `timings_seconds` with `prepare`, `ttft`, `vision`, `prefill`,
  `decode`, `total`, plus a `speculative` block with `drafted_tokens`, `accepted_tokens` and
  `rounds`.

AdaScope's `parse_jsonl` reads `timings.predicted_per_second` from a `request_done` record. No
such key exists in schema v20; `predicted_per_second` lives in the HTTP reply. So the fidelity
test as described in `docs/MILESTONE-1.md` C11 cannot work against the JSONL alone. Pin one of
two paths before C11: read the field from the HTTP reply, or derive the per-request rate from
`timings_seconds.decode` and the completion token count. Both are independent of the counter-delta
method, which is what makes A2 real evidence rather than a tautology.

### The experiment's own record

The frozen `Run` has no field for "which cause was seeded" or "what the verdict was". Do not add
one; the schema is frozen for Phase 1. `Run.artifacts` is a list of paths, so the eval writes
`runs/<run_id>.eval.json` next to the run file and lists it in `Run.artifacts`. Its format:

```json
{
  "stage": "E2",
  "repetition": 3,
  "seeded_cause": "sm89.power-cap-limit",
  "variable": {"name": "power_limit_w", "baseline": 450, "treatment": 250},
  "top_rule_id": "sm89.power-cap-limit",
  "verdict": "confirmed",
  "reason": "throttle.sw_power_cap true in steady window; roof rule did not fire"
}
```

`verdict` is one of `confirmed`, `rejected`, `inconclusive`. This keeps the report a pure function
of stored data while leaving the experiment's identity in the same directory as the run.

## (f) Tests required, and which must skip

| Test | Asserts | Needs GPU | Needs server | Needs root |
| --- | --- | --- | --- | --- |
| `tests/test_smoke.py` | discovery finds tests | no | no | no |
| `tests/test_model.py` | round trip, tuple samples, enum values | no | no | no |
| `tests/test_store.py` | save, load, idempotent resave, `.tmp` ignored | no | no | no |
| `tests/test_reference.py` | A3 | no | no | no |
| `tests/test_engine.py` | predicate shapes, the three rules fire and stay quiet on synthetic facts | no | no | no |
| `tests/test_analyze.py` | `power_ratio`, `objective_ratio`, `temp_c`, throttle OR-over-window, ranked order, deterministic ties | no | no | no |
| `tests/test_report.py` | A1, A7, golden text | no | no | no |
| `tests/test_acceptance.py` | A1 and A2 from a stored fixture; a live A2 variant when both guards pass | fixture: no | fixture: no | no |
| `tests/test_nvml.py` | discover matches this card, sample keys, `nvidia-smi` cross-check | yes | no | no |
| `tests/test_lmcompat.py` | Prometheus parser and JSONL parser (pure, unguarded); live counters and model list (guarded) | no | mixed | no |
| `tests/test_cli_observe.py` | target parsing and rejection (unguarded); end-to-end observe and load (guarded) | mixed | mixed | no |
| `tests/eval_induced_bottleneck.py` | A4, A5, A6, A8 | yes | yes | yes for E2 |

Guard rules, per `AGENTS.md`:

- Hardware tests use `@unittest.skipUnless(nvml_available(), ...)`, with `nvml_available()`
  memoised in a shared `tests/support.py` so no module performs a side effect at import time. A
  skip is not a pass: the eval records which stage was skipped and why.
- Network tests probe reachability once and skip with the reason, for example "engine at
  `127.0.0.1:5804` is down".
- The eval script skips E2 with an explicit message when `nvidia-smi -pl` fails, and skips every
  live stage when free VRAM is below the artifact size plus a margin. Today both skips fire.
- The suite must still pass with no GPU, no server and no root: of the 11 modules listed above,
  7 run in full, 3 run partially (their pure tests execute and their live tests skip), and the
  hardware-only module skips cleanly.

## (g) The three largest technical uncertainties

### 1. Is the ceiling a stable predictor at all?

The reference model's output is only as good as `spec_tokens_per_forward`, which is measured from
two engine counters. If acceptance drifts between repetitions, `objective_ratio` is noise dressed
as a ratio, and every rule that keys off it inherits the noise.

**Evidence that would resolve it.** A6: the coefficient of variation of the factor across five
fixed-configuration repetitions. Alongside it, the agreement between the counter-delta rate and
the engine's own per-request rate on the same window (A2, 1 percent). If the factor's CV is at or
below 5 percent and A2 holds, the predictor stands. If the CV is large, the honest output is that
no ceiling can be stated on this workload, which is a finding worth publishing.

This is already the largest live risk, and one case is quantified in (c): the factor from the
draft counters (1.6635) and the factor implied by the recorded rate (1.97) disagree by about 18
percent, and the first one puts the measured rate above its own ceiling. Settled 2026-11-16
without a GPU: the factor from the counters is 3.0195 by the committed/(committed - accepted)
algebra, the ceiling is 167.13, and the ratio is 0.6527. What remains live is the A6 half,
the factor's coefficient of variation across fixed-configuration repetitions, which only a
clean E1 can measure.

### 2. Is the attribution specific, or a restatement of one arithmetic comparison?

The two rules that matter here partition `objective_ratio` at 0.9: the roof rule fires above it,
the power-cap rule requires below it plus `power_ratio >= 0.95`. A capped run therefore satisfies
the power-cap predicate almost by construction. The eval can pass while the telemetry contributes
nothing.

**Evidence that would resolve it.** Two adversarial fixtures and one control. (i) A fixture with
`power_ratio >= 0.95` and `throttle.sw_power_cap` false, where the cap rule's confidence must be
"supported" and not "measured" -- if it prints measured, the rule cites evidence it does not have.
(ii) A fixture where both rules would fire, which must rank deterministically and must not claim
two incompatible limiting resources. (iii) The control run (E1), where the cap rule must stay
quiet. A5 covers the live half.

### 3. Can the measurement path run here, and does the engine's data support the fidelity claim?

Three independent preconditions and one unknown data shape stand between this design and a result.
The engine is down; the card has 7108 MiB free against a 16.96 GiB artifact; the power-limit
write needs a password this session does not have; and the per-request rate's field name in the
request log differs from the name AdaScope's reader assumes.

**Evidence that would resolve it.** Four concrete reads: `curl` on `127.0.0.1:5804/health`
returns ok; `nvidia-smi --query-gpu=memory.free` exceeds 18210531328 bytes plus KV overhead;
`nvidia-smi -pl 250` either succeeds or fails with a permission error; and one real
`request_done` line printed, showing which key holds the decode rate. The last one is the
cheapest and the most likely to change the C11 design.

## Inconclusive is a valid outcome

The design admits "the evidence is inconclusive" as a result, not as an error, in four cases:

| Case | Recorded as |
| --- | --- |
| A precondition fails (engine down, card contended, no permission) | `verdict: "inconclusive"`, `reason` naming the failed precondition, and the stage marked skipped |
| A6 fails: the speculative factor is unstable | `verdict: "inconclusive"`, `reason: "spec factor CV above 5 percent"` |
| A5 fails: the throttle bit contradicts the claimed cause | `verdict: "inconclusive"`, `reason` quoting the bit's value |
| Two rules tie for first rank | `verdict: "inconclusive"`, `reason` listing both rule ids |

Recording it is the eval's job, in `runs/<run_id>.eval.json`, and the eval prints a one-line
summary. No test may convert an inconclusive record into a pass, and no report may present an
inconclusive result as a diagnosis. A milestone whose first honest result is "the evidence does
not identify a limit" is a milestone that worked.
