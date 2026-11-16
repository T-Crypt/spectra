# Prior art, and what Spectra could still contribute

The survey behind Milestone 1. It reviews the established practice Spectra is built on, records
what the tools already on this machine already answer, and shrinks Spectra's claimed
contribution to the parts that survive that review.

## How to read the evidence marks

| Mark | Meaning |
| --- | --- |
| verified | A command was run on this machine, or a source was fetched, on 2026-10-15. The text quotes what it actually said |
| documented | An official document states it. Fetching that document during this survey is noted |
| practice | Common engineering practice, described from general knowledge. No citation is claimed |
| unverified | Asserted somewhere in a predecessor document and not checked here. Treat it as a lead, not a fact |

Predecessor research notes exist at `T-Crypt/SMTrace@e70874c:docs/drafts/research-profiler.md`.
Their claims are marked below. One of their citations is already dead: the URL
`https://developer.nvidia.com/nvidia-development-tools-solutions-err_nvgpucounterperm` now
returns a "Page Not Found" page (verified 2026-10-15).

## 1. Roofline and performance-model analysis

A performance model turns "this is slow" into "this is slow relative to a stated bound". The
roofline form of that idea plots achievable throughput against operational intensity and draws
two bounds: a memory-bandwidth slope and a compute plateau. The result is a per-kernel verdict of
bandwidth-bound or compute-bound, with the distance to the bound as the headroom. The attribution
to Williams, Waterman and Patterson's 2009 work is **unverified** here; the paper was not
fetched. Treat the attribution as a lead.

What is verified is that the toolchain implements it: NVIDIA's own Nsight Compute Profiling Guide
lists roofline charts as report sections, including `SpeedOfLight_HierarchicalRooflineChart`,
described as "High-level overview of the utilization for compute and memory resources of the GPU
presented as a roofline chart" (documented; the guide at
`https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html` was fetched and returned 200
on 2026-10-15).

The limitation that matters for Spectra is that a roofline bound is per kernel and per counter
set. It says nothing about an implementation that reaches only 40 percent of the weight-read
bandwidth because it issues the work badly, or because the host cannot feed it, or because the
power cap lowered the clocks the bound is written against.

What Spectra does instead is a workload-level version of the same move, at a coarser grain:
`docs/DESIGN.md` derives a ceiling for dense decode from weight bytes per forward pass, a
documented bandwidth, and the tokens produced per forward pass. That derivation is arithmetic, it
needs no profiler, and it is falsifiable by measurement. Its weakness is the same as the
roofline's: it is an upper bound under assumptions, and every assumption has to be listed.

## 2. The NVIDIA profiling toolchain, and what each tool cannot do

| Tool | What it produces | What it cannot tell you | On this machine |
| --- | --- | --- | --- |
| `nvidia-smi` / NVML | Power draw and configured limit, SM and memory clocks, temperature, VRAM used and free, utilisation, named throttle reason bits, driver and CUDA versions, the processes holding the device | Nothing about the workload. It knows the card, not the work | Present and working. Read-only queries need no privileges |
| Nsight Systems (`nsys`) | A host and device timeline: kernel durations, runtime and driver API calls, synchronisation, memory transfers, idle gaps (practice; the User Guide was not fetched here) | Kernel-internal behaviour. It is not a counter profiler | Not installed: `command -v ncu nsys` finds neither (verified) |
| Nsight Compute (`ncu`) | Per-kernel hardware counters: occupancy, warp stall reasons, memory throughput, cache hit rates, register and shared-memory use, instruction mix (practice), and roofline charts (documented: the Profiling Guide lists `SpeedOfLight_HierarchicalRooflineChart` and siblings). Counter collection replays the kernel: the CLI documentation lists "replay iterations", "replay buffer location" and "Replay individual kernel launches", and describes "replaying a kernel launch multiple times" to collect metrics (documented, Nsight Compute CLI docs, fetched 200 on 2026-10-15) | Run-level behaviour, host overhead, and anything about a kernel it cannot launch | Not installed |
| CUPTI | The low-level interface under nsys and ncu: kernel events, API calls, transfers, NVTX ranges (practice; not verifiable here, neither tool is installed) | Same as the tool built on it | Not installed |
| DCGM | Datacenter GPU management: health, telemetry and counters for datacenter parts | GeForce support is **unverified**. Datacenter focus is the widely stated scope | `dcgmi` is not installed (verified) |

`ncu` permission behaviour, documented: "ERR_NVGPUCTRPERM - The user does not have permission to
access NVIDIA GPU Performance Counters on the target device. By default, NVIDIA drivers require
elevated permissions to access GPU performance counters. On mobile platforms, profile as
root/using sudo. On other platforms, you can either start profiling as root/using sudo, or by
enabling non-admin profiling." (documented, Nsight Compute Profiling Guide, fetched 2026-10-15).

That corrects one claim in SMTrace's research note, which says there is no supported unprivileged
workaround on Linux. The current guide offers root/`sudo` or enabling non-admin profiling. Whether
either path works on this GeForce card with this driver is **unverified**, because `ncu` is not
installed.

The profiler-speedup figures in SMTrace's note (roughly 1.3x to 3x for nsys, 10x to 100x for ncu)
are **unverified** here and should be measured per workload before any document depends on them.

Consequence for Spectra: on this machine, in Phase 1, the only tier available is telemetry plus
engine counters. Every rule must be falsifiable with those, and any rule that needs a counter
must be declared as unavailable rather than estimated.

## 3. LLM prefill versus decode

Practice, stated plainly: prefill processes a whole prompt at once, so it presents large matmuls
with real reuse and tends toward compute-bound; decode produces one token per forward pass while
reading the weights again, so it tends toward memory-bandwidth-bound. This is **practice**, not a
citation, and it is not universal: a batched decode step with a large batch becomes compute-heavy,
and a prefill with a long context and a small model is bandwidth-heavy.

What the local engine's own published work shows is consistent with the decode half of it. In
`ninfer`'s Qwen3.8-27B page (documented; `docs/performance/qwen3.8-27b.md` in
`/home/tcrypt/wt/ninfer-v3`, HEAD `e85e028`), the measured no-speculation groupwise-int profile
on an RTX 5090 gives decode phase rates falling as context grows:

| Prompt tokens | Decode phase (tok/s) |
| --- | --- |
| 7,680 | 79.8 ± 0.4 |
| 64,512 | 73.6 ± 0.4 |
| 130,048 | 66.3 ± 0.4 |
| 260,096 | 56.2 ± 0.6 |

Prefill in the same table falls from 3,274.7 to 1,609.7 tok/s. A decode rate that declines roughly
with context is what a per-forward byte cost that grows with the KV read predicts. That is
supporting evidence for the shape of Spectra's reference model, not proof of it: the engine's
number is measured on a different card, and the decode rate also carries harness and sampling
differences.

The phrase that matters for the benchmark design is in the same document: "The three decode rates
have different time denominators and must not share an unlabeled column." Spectra's rule that
every number is labeled measured, derived or hypothesis is the same idea, applied to the report.

## 4. Workload fingerprinting and regression detection

The idea is standard practice: record enough identity to know whether a performance result can be
compared to another one, then detect change against that identity.

SMTrace's version of it is a **document-only** design: a fingerprint schema with per-metric
provenance, a phase array, run dispersion as a min/max range and an explicit `value_status`
vocabulary that keeps `unavailable` distinct from an estimate
(`T-Crypt/SMTrace@e70874c:README.md` "Proposed Data Model", and
`docs/drafts/rewrite-data-model.md`). No code exists. Its one acceptance criterion worth carrying
forward is the honest comparison: if a material variable differs, report inconclusive rather than
a speedup.

The local engine already practices the parts that matter, and documents them as rules
(documented, `ninfer` `docs/performance/methodology.md`):

- Each published point records the campaign date, the weights identity, the tested Git revision,
  concurrency, context ceiling and KV capacity.
- Comparison is optional, and when made must identify both run IDs, the metric, and any
  configuration or workload difference. Throughput speedup is `new / baseline`; makespan speedup
  is `baseline / new`.
- "Historical comparisons do not isolate a backend change." and "MTP0 context profiles and
  speculative scenario suites use different workloads and cannot establish per-scenario
  baseline/speculative speedups."
- Repeated samples: five per context for the context profile, with ± dispersion published.
- Unavailable or uninteresting metrics are excluded rather than estimated, and pathological
  samples are retained and labeled.

That is a workload-identity discipline with published numbers, and it exists today without
Spectra. It is the strongest evidence in this survey for Spectra narrowing what it claims: the
engine owns its own fingerprint and its own comparison rules.

## 5. Controlled experimental design

Practice, and the part of this project with the least novelty: one independent variable per
experiment, a control run, a stated success criterion with a threshold, repeated runs with
dispersion reported, and a record of the result including the negative ones.

The local engine already implements the measurement hygiene half: warm-up and startup outside
measured requests and waves; steady throughput restricted to complete one-second intervals with
zero prefill tokens, `running=C`, `prefilling=0`, `decode_ready=C`, at least one decode round and
exactly C rows in every round; ramp-up, prefill and drain excluded (documented,
`docs/performance/methodology.md`).

What is not in place anywhere locally is the part Spectra's `docs/DESIGN.md` claims: choosing
which experiment to run next because it discriminates between the hypotheses still standing.
That is a real gap, and it is a design idea, not a measured result.

## 6. The existing local workflow (verified inventory)

Everything in this section was read or run on 2026-10-15.

**The card.** `nvidia-smi`: NVIDIA GeForce RTX 4090, driver 615.78.08, CUDA UMD version 13.4,
24564 MiB, power limit 450 W, default 450 W, max 480 W, 19 W draw, 23 C, P8, 0 percent
utilisation, `clocks_throttle_reasons.active` = `0x0000000000000001` (idle), compute mode
Default, persistence Disabled.

**Contention.** `nvidia-smi --query-compute-apps=pid,process_name,used_memory` returns exactly one
row: pid 1293313, `/home/tcrypt/comfy/.venv/bin/python`, 17023 MiB. `nvidia-smi
--query-gpu=memory.free` reports 7108 MiB free of 24564 MiB. The milestone's artifact,
`/home/tcrypt/ninfer-4090/models/qwen3_8_27b.ninfer`, is 18210531328 bytes (16.96 GiB) on disk, so
it cannot load while that process holds the card.

**NVML from Python.** Adascope's ctypes adapter ran here during this audit: its three NVML tests
passed while ComfyUI held 17 GiB. `libnvidia-ml.so.1` loads and read-only calls work unprivileged.

**Power-limit writes.** `sudo -n true` fails with "sudo: a password is required" (verified). Any
experiment that sets `nvidia-smi -pl` cannot run unattended as this user.

**The inference engine.** `127.0.0.1:5804` is down: `curl /health` returns nothing. `llama-swap` is
up on `127.0.0.1:9090` (pid 75086) and serves its own Prometheus endpoint.

**Engine counters** (documented; read from source at
`/home/tcrypt/wt/ninfer-v3` HEAD `e85e028`, file `src/serve/serve_metrics.cpp`). Ten series total:

| Counter | Meaning |
| --- | --- |
| `llamacpp:prompt_tokens_total` | Computed prefill tokens |
| `llamacpp:prompt_seconds_total` | Prefill seconds |
| `llamacpp:tokens_predicted_total` | Committed decode tokens |
| `llamacpp:tokens_predicted_seconds_total` | Decode seconds |
| `llamacpp:requests_processing` | Requests at or under the concurrency limit |
| `llamacpp:requests_deferred` | Requests over the limit |
| `ninfer:requests_total` | Requests served |
| `ninfer:prefix_cache_hit_tokens_total` | Prefix-cache hit tokens |
| `ninfer:draft_tokens_total` | Speculative draft tokens |
| `ninfer:draft_accepted_tokens_total` | Accepted draft tokens |

**Per-request timings.** Two producers, and they are not the same one:

- The OpenAI-compatible response body carries a `timings` block including
  `predicted_per_second` (documented, `src/serve/openai_chat_response.cpp:100`).
- The JSONL request log, enabled with `--request-log-jsonl`
  (`src/serve/serve_options.cpp:284`), schema version 20
  (`src/serve/request_log.h:23`, `kRequestLogSchemaVersion = 20`). A `request_done` record carries
  `timings_seconds` with `prepare`, `ttft`, `vision`, `prefill`, `decode`, `total`; a
  `speculative` block with `drafted_tokens`, `accepted_tokens`, `rounds`, `accepted_per_position`;
  `engine_timing` with `queue_wait_seconds`, `host_exposed_seconds` (five sub-counters plus
  `total`), `device_wait_exposed_seconds`, and a `decode` split into host-exposed and device-wait;
  and a `materialization` block. A separate `throughput` event carries
  `throughput_tokens_per_second` = `{prefill, decode}`, `tokens` = `{computed_prefill,
  committed_decode}` and a scheduler block (documented; read from `src/serve/request_log.cpp`).

This matters for the port: Adascope's JSONL reader looks for
`request_done.timings.predicted_per_second`. The v20 `request_done` record has no such key; the
per-request rate must be derived from `timings_seconds.decode` and the completion token count, or
read from the HTTP reply. See `docs/EVAL.md`.

**Engine benchmark tooling already shipped** (documented; all present under
`/home/tcrypt/wt/ninfer-v3`): `tools/bench/README.md`, an external Serve TTFT client with its own
controller that starts and stops the server per sample, stages the artifact, stores raw artifacts
and writes Markdown, JSON and CSV summaries (`tools/bench/ttft/`); a list of scenario runners
(`run_serve_ttft_campaign.py`, `run_serve_concurrency.py`, `run_qwen38_mtp_sweep.py` and others);
the `ninfer_bench` throughput tool under `bench/`; and `docs/performance/methodology.md` as the
measurement and publication contract.

**Other local tooling.** `llama-swap` `/metrics` on port 9090 publishes 16 gauge names, including
`llamaswap_gpu_power_draw_watts`, `llamaswap_gpu_temperature_celsius`,
`llamaswap_gpu_memory_used_bytes` and `llamaswap_gpu_util_percent`. It publishes no token
throughput. `/usr/local/bin` holds `llama-bench`, `llama-server`, `llama-swap` and
`llama-server.b11115-pre-fastmtp`; both llama binaries report "version: 0.6.0-dev (build 1, commit
fcac190)". The 2026-10-10 handoff brief recorded them as v0.4.1-dev, so that fact is stale. A
`llama-bench --help` invocation also printed "ggml_cuda_init: failed to initialize CUDA: no
CUDA-capable device is detected" before printing its usage, which is a live environment symptom
worth explaining before any llama.cpp measurement is trusted; the cause is **unverified**.
`/home/tcrypt/homelab/scripts/ninfer/` holds `prefill_bench.py` and `sweep.py`.

## 7. What existing tools already solve

The point of this section is to remove work from the plan. Where a tool already answers a
question, Spectra must consume the answer, not rebuild it.

| Question | Already answered by | Spectra's residual |
| --- | --- | --- |
| How fast is this engine decoding right now? | `llamacpp:tokens_predicted_total` and `..._seconds_total`, plus the response `timings` block | None for the number itself. Spectra's only claim is that it stores the raw series so the number can be recomputed later without a rerun |
| How does decode rate vary with context on this engine? | The engine's own context profiles, measured, published with dispersion | None. Spectra must not re-run this campaign |
| Is the card power-capped or thermally throttled? | `nvidia-smi -q -d PERFORMANCE` and the NVML throttle bits | None for the fact. Spectra adds storage and the link from that fact to a stated cause |
| Is another process competing for the card? | `nvidia-smi --query-compute-apps` | None. Spectra should record it in the run, not recompute it |
| What is the kernel-level bottleneck of this kernel? | `ncu`, including roofline charts and stall reasons | Nothing today: `ncu` is not installed, and on GeForce the counters need elevated permission. Spectra must declare this tier unavailable rather than approximate it |
| Is host-side submission the problem? | `nsys`, and the engine's own `host_exposed_seconds` / `device_wait_exposed_seconds` split | The engine already splits host-exposed from device-wait time per request. Consume that before any tracer |
| Was this measurement taken under the same conditions as that one? | The engine's run records: revision, weights identity, campaign date, concurrency, KV capacity, sampling | A cross-run and cross-engine comparability rule. The engine states the rule for its own results; nothing states it across engines |
| Are these two runs comparable at all? | Nothing local, and SMTrace's design is documentation only | This is a genuine gap, and it is Spectra's strongest candidate |
| Reproduce this number | Each published point links its reproduction command and artifact path | None |

The honest conclusion: for a single run of a single engine, Spectra currently adds nothing that
the engine does not already publish. What it can add is memory, comparability and attribution.

> **Update 2026-11-16.** The contention row above is now implemented, not just specified:
> `observe` enumerates the card's compute processes every tick (`Nvml.processes()`),
> stores a first-tick snapshot in `Run.environment`, and the report prints the list.
> A second process on the card fires the `sm89.gpu-co-tenant` rule at measured
> confidence. One correction to this section's finding: the NVML process
> enumerator needs root on this driver (NVML error 7), unlike the sample
> calls; the unprivileged path falls back to the same table from
> `nvidia-smi`, and the run records which enumerator produced the list
> (`gpu_processes_method`). What was not implemented: the comparability
> rows, which stay open.

## 8. Candidate differentiators

Each entry is a research direction, not an established result, and each states what would falsify
it.

**1. Cross-run and cross-engine comparison with explicit compatibility rules.**
Direction: a stored run carries enough identity that Spectra can declare two runs comparable,
comparable after normalization, or not comparable, and say which field broke it.
Falsified if: on a set of runs with a known material difference (a different context length, a
different weights format, a different speculative setting), the rule either accepts an
incomparable pair or rejects a comparable one. This is measurable against the engine's own run
metadata, which names the differences.

**2. Evidence-linked diagnosis instead of utilization-based explanation.**
Direction: every diagnostic names the observation, its source series, the method, and the
confidence basis, so a reader can reject the diagnosis by rejecting a number.
Falsified if: a diagnosis fires with no observation that supports it, or the same evidence set
produces a different ranking on a repeated render. The second half is cheap to test today:
render twice and compare bytes.

**3. Automated selection of the discriminating experiment.**
Direction: from the set of hypotheses still standing, pick the one config change that best
separates them, and predict the outcome before running it.
Falsified if: the selected experiment fails to separate the hypotheses more often than a fixed
order would, measured over the seeded cases in `docs/EVAL.md`. Until that comparison exists, this
is a not-yet-tested idea.

**4. Fingerprints tied to exact workload and environment identity.**
Direction: a stored run identifies the artifact by size and hash, the engine by version and
config, the hardware by profile revision, and the environment by contention state.
Falsified if: two runs that differ in a way that changes throughput carry the same fingerprint
and the comparison rule declares them compatible. The card today makes this testable without
waiting: a run under ComfyUI's 17 GiB and a run on an idle card differ in environment only.

**5. Explicit uncertainty when profiling data is incomplete.**
Direction: a missing metric is `unavailable`, never estimated, and a diagnosis built without it
says so in the report.
Falsified if: any report line presents an estimated or unavailable value as measured, or if a
rule fires on a metric the run does not contain. SMTrace's vocabulary already states the rule;
the falsification is a one-line test over a run with a deliberately missing series.

Two candidates from the predecessor documents should be dropped rather than carried:

- A dashboard or GUI (`ROADMAP.md` Phase 6). `docs/DESIGN.md` already argues the unit of value is
  not a dashboard, and no Phase 1 result depends on one.
- A reimplementation of profiling tiers. `ncu` and `nsys` are not installed, and their counter
  semantics cannot be reproduced from telemetry.

## 9. Unverified claims carried forward

These appear in the predecessor documents or in `docs/DESIGN.md` and were not confirmed here.
They should not be relied on until measured.

| Claim | Where | State |
| --- | --- | --- |
| Roofline model attribution to Williams, Waterman and Patterson (2009) | practice knowledge | unverified; paper not fetched |
| nsys adds 1.3x to 3x wall-clock | `SMTrace@e70874c:docs/drafts/research-profiler.md` | unverified; nsys not installed |
| ncu slows a profiled kernel by 10x to 100x | Same | unverified; ncu not installed |
| Sub-100 ms `nvidia-smi` polling is unreliable | Same | unverified |
| DCGM does not support GeForce | Same | unverified; `dcgmi` not installed |
| Clock locking on GeForce is blocked or ignored on many driver versions | Same | unverified here |
| `ninfer`'s internal file layout, `src/serve/*.cpp` line numbers | `docs/DESIGN.md`, "Relationship to an existing engine" | The files exist at the paths named, at HEAD `e85e028`. Line numbers were not checked |
| `pynvml` is not installed and telemetry must shell out to `nvidia-smi` | Handoff brief, 2026-10-10 | Superseded: the NVML ctypes path works here and is what AdaScope implemented |
| `llama-bench` is v0.4.1-dev | Handoff brief, 2026-10-10 | Stale: it reports 0.6.0-dev, commit `fcac190` |
| The test machine has "no numpy" | `docs/DESIGN.md` | Incorrect today: numpy 2.5.4 is installed for `/usr/bin/python` 3.14.8 |
