# SMTrace

Architecture-aware GPU workload fingerprinting, bottleneck diagnosis, and optimization experiments.

SMTrace is a GPU engineering and performance analysis project designed to explain why CUDA workloads and inference engines behave differently on the same hardware.

Rather than reporting utilization and throughput alone, SMTrace correlates workload configuration, execution traces, GPU telemetry, and hardware profiling counters to identify likely performance constraints and propose controlled experiments.

The initial target is NVIDIA Ada Lovelace (sm_89), with a focus on local AI inference, CUDA workloads, and repeatable performance comparisons.

Measure the workload. Identify the bottleneck. Test a hypothesis. Keep only what the evidence proves.

---

## Table of Contents

* [The Problem](#the-problem)
* [Project Vision](#project-vision)
* [What Makes SMTrace Different](#what-makes-smtrace-different)
* [Workload Fingerprinting](#workload-fingerprinting)
* [Bottleneck Analysis](#bottleneck-analysis)
* [Inference Workload Analysis](#inference-workload-analysis)
* [Differential Performance Analysis](#differential-performance-analysis)
* [Optimization Engine](#optimization-engine)
* [Architecture and Data Flow](#architecture-and-data-flow)
* [Profiling Tiers](#profiling-tiers)
* [Diagnostic Methodology](#diagnostic-methodology)
* [Interface Design](#interface-design)
* [Proposed Data Model](#proposed-data-model)
* [Implementation Roadmap](#implementation-roadmap)
* [Initial Acceptance Criteria](#initial-acceptance-criteria)
* [Technical Challenges](#technical-challenges)
* [Design Principles](#design-principles)
* [Open Decisions](#open-decisions)
* [Long-Term Direction](#long-term-direction)
* [Project Status](#project-status)
* [License](#license)

---

## The Problem

GPU performance analysis stops at observing symptoms.

A monitoring dashboard may report high utilization, substantial VRAM consumption, or a power limit. A profiler may expose kernel timings and hardware counters. A benchmark may report tokens per second.

These measurements are useful, but they do not explain why a workload performs the way it does or what change is likely to improve it.

A CUDA workload can be limited by:

* Compute throughput.
* Memory bandwidth or data movement.
* Kernel launch and synchronization overhead.
* Insufficient latency hiding.
* Register or shared-memory resource constraints.
* Power, voltage, clock, or thermal behavior.
* CPU-side execution and data preparation.
* PCIe transfers or other host-device communication.
* Runtime scheduling, batching, or inference-engine implementation.
* Interactions between multiple bottlenecks.

These constraints can overlap or change as workload parameters change.

A workload that is memory-bound during token generation may behave differently during prompt processing. A configuration that performs well at a short context length may degrade at a longer one. Two inference engines may report similar GPU utilization while delivering different throughput.

The missing layer is a reproducible methodology that connects performance observations to defensible explanations and controlled optimization experiments.

## Project Vision

SMTrace aims to build a hardware-aware performance investigation system around three core capabilities.

1. Workload fingerprinting

Capture the hardware, software, workload, configuration, measurements, and environmental conditions needed to reproduce a performance result.

2. Evidence-backed diagnosis

Correlate available telemetry, execution traces, and hardware counters to identify candidate bottlenecks and explain the evidence supporting each hypothesis.

3. Controlled optimization

Design experiments that isolate variables, measure their effects, and retain successful optimizations as reproducible results.

The goal is not to automate arbitrary tuning or produce a single synthetic GPU score. It is to explain performance behavior and establish which changes improve a specific workload.

## What Makes SMTrace Different

SMTrace is not intended to replace NVIDIA Nsight Systems, Nsight Compute, CUDA, or the inference engines being measured.

Those tools already provide tracing, profiling, and hardware analysis capabilities. SMTrace should use them where appropriate and focus on the workflow that connects measurement to action.

**Architecture-aware analysis**

Interpret measurements in the context of the GPU architecture, supported instructions, resource constraints, workload shape, and available profiling capabilities.

The initial target is NVIDIA Ada Lovelace, compute capability 8.9 (sm_89).

**Comparable workload fingerprints**

Compare runs only when their workload definitions and measurement conditions support a meaningful comparison.

When important variables differ, SMTrace should identify those differences, normalize them where defensible, or mark the comparison as inconclusive.

**Differential diagnosis**

Investigate why two runs differ rather than reporting that they differ.

Correlate performance changes with observable differences in kernel execution, memory behavior, clocks, power, synchronization, and workload configuration.

**Hypothesis-driven optimization**

Every recommendation should identify the observation, proposed explanation, experiment, expected outcome, success criteria, and alternative interpretations.

**A growing library of validated results**

Preserve both successful and unsuccessful experiments so that future investigations can reuse prior evidence without assuming that an optimization applies to every workload.

The long-term differentiator is the accumulated relationship between hardware, workload characteristics, performance signatures, diagnostic hypotheses, and experimentally verified outcomes.

## Workload Fingerprinting

A workload fingerprint is a structured record of how a workload behaves under a defined environment and configuration.

It should capture enough information to reproduce the experiment and determine whether another run is comparable.

**Hardware identity**

* GPU model and architecture.
* Compute capability.
* VRAM capacity.
* Driver and CUDA runtime versions.
* Available power and clock telemetry.
* Relevant hardware and profiling capabilities.

**Software identity**

* Inference engine or application.
* Engine version and build configuration.
* CUDA libraries and relevant dependencies.
* Model-loading and execution options.
* Profiling tools and versions, where used.

**Workload identity**

* Model identifier and file hash, where applicable.
* Model architecture and quantization format.
* Prompt or workload definition.
* Input and output lengths.
* Batch size and concurrency.
* Context length.
* GPU offload configuration.
* Relevant runtime parameters and random seeds where applicable.

SMTrace should not retain sensitive prompts and model inputs by default to establish a fingerprint. A workload can use a locally stored fixture, a content hash, or an explicit opt-in capture policy.

**Performance signature**

* Throughput.
* Latency distributions.
* Time to first token.
* Inter-token latency.
* VRAM allocation and headroom.
* Power and clock behavior.
* Temperature and thermal events.
* CPU activity.
* Kernel execution timings.
* Memory bandwidth and other profiling counters where available.
* Measurement overhead and collection limitations.

**Diagnostic signature**

* Candidate bottlenecks.
* Supporting measurements.
* Confidence and evidence quality.
* Alternative hypotheses.
* Proposed experiments.
* Previous experiment outcomes.
* Validated optimization profiles.

Every metric should carry its own provenance. Each measurement records its collection source, tool and version, measurement interval, units, availability status, known collection overhead, and whether the value is measured, derived, estimated, or unavailable.

SMTrace must distinguish measured facts from derived metrics, estimated values, and model-generated hypotheses.

## Bottleneck Analysis

SMTrace should support multiple simultaneous bottleneck hypotheses instead of assigning each workload a single permanent classification.

**Compute throughput**

Determine whether useful arithmetic execution is approaching a relevant hardware throughput limit.

Investigate:

* SM activity.
* Instruction throughput where available.
* Achieved versus theoretical throughput.
* Arithmetic intensity.
* Eligible warps and execution-pipeline utilization where supported.
* Kernel-level execution characteristics.

Potential experiments include changing workload shape, batch size, precision, or kernel implementation.

High SM utilization alone does not prove that arithmetic throughput is the limiting factor.

**Memory bandwidth and data movement**

Investigate whether the workload is constrained by memory traffic, cache behavior, or data movement between memory levels.

Relevant evidence includes:

* Measured DRAM throughput.
* Memory transactions and bytes transferred.
* Cache hit rates.
* Effective memory traffic per operation or generated token.
* Arithmetic intensity.
* Host-device transfer behavior.

Potential experiments include changing batch size, data layout, quantization, caching behavior, or concurrency.

VRAM allocation and memory bandwidth utilization must remain distinct measurements. A large allocation does not imply saturated bandwidth.

**Kernel launch and synchronization overhead**

Identify workloads where CPU-side submission, synchronization, or gaps between GPU operations affect total execution time.

Investigate:

* Kernel duration distributions.
* Kernel launch frequency.
* CPU submission activity.
* GPU idle gaps.
* Synchronization points.
* Graph execution or batching opportunities.

Potential experiments include CUDA Graphs, batching, reduced synchronization, or alternative execution paths where supported.

Short kernels are not inherently inefficient. The important measurement is overhead relative to useful work.

**Occupancy and latency hiding**

Investigate whether a kernel has insufficient active or eligible warps to hide execution latency.

Relevant evidence may include:

* Registers per thread.
* Shared-memory use per block.
* Theoretical and achieved occupancy.
* Eligible warps per cycle.
* Supported stall-reason metrics.
* Resource allocation constraints.

Potential experiments include comparing kernel variants or resource configurations.

Higher occupancy is not automatically faster. Additional registers or reduced occupancy may improve overall performance when they enable better instructions, less data movement, or more efficient execution.

**Power, clocks, and thermals**

Correlate performance changes with power draw, clock behavior, thermal conditions, and available throttle-reason telemetry.

Investigate:

* Sustained clock behavior.
* Power draw relative to configured limits.
* Temperature over time.
* Performance-state changes.
* Thermal or power-related throttling.
* Throughput degradation during sustained runs.

Potential experiments may include controlled power targets or cooling conditions.

A reported power-limit condition is not sufficient evidence that changing the power limit will improve performance. Every proposed change must be validated against the workload's actual objective.

**CPU and system-level constraints**

Determine whether the GPU is waiting for host-side work or data.

Investigate:

* CPU activity by thread.
* Tokenization and data preparation.
* Host-to-device transfers.
* GPU idle intervals.
* Synchronization overhead.
* Page faults or memory pressure where observable.
* Storage activity when it affects workload execution.

High CPU utilization alone does not prove that the CPU is the bottleneck. The diagnosis should connect host-side activity to the workload timeline.

## Inference Workload Analysis

Local LLM inference is an initial target because its execution phases have different performance characteristics and measurable objectives.

**Prefill**

Prefill processes the input prompt and constructs the KV cache.

Investigate:

* Prompt tokens per second.
* Time to first token.
* Prompt length and batch dimensions.
* Kernel execution behavior.
* Memory traffic.
* GPU utilization and power behavior.

Larger prompt batches may expose compute throughput constraints, while memory traffic and execution overhead can still be significant.

**Decode**

Decode generates tokens autoregressively.

Investigate:

* Decode tokens per second.
* Inter-token latency.
* Batch size and concurrent sequences.
* Context length.
* Model-weight traffic.
* Memory bandwidth where measurable.
* Kernel execution and synchronization behavior.

At small batch sizes, model-weight traffic can be large relative to useful arithmetic. However, the actual limiting factor depends on the model, quantization, kernel implementation, and runtime configuration.

**Long-context behavior**

Longer contexts change KV-cache requirements and can alter attention costs, memory traffic, latency, and throughput.

Investigate:

* Context length.
* KV-cache allocation and growth.
* Memory headroom.
* Prefill latency.
* Decode throughput as context grows.
* Memory bandwidth and cache behavior where measurable.
* Allocation failures and performance thresholds.

SMTrace should compare workload phases independently instead of collapsing all inference performance into one aggregate score.

## Differential Performance Analysis

A core feature is explaining why two runs behave differently.

Consider the same model executed through two inference engines on the same GPU.

A benchmark may show that one engine generates tokens faster. SMTrace should investigate whether the difference correlates with:

* Kernel selection or implementation.
* Number and duration of kernel launches.
* GPU idle gaps.
* Memory traffic.
* Batch scheduling.
* CPU overhead.
* Synchronization.
* Power and clock behavior.
* Different execution settings.

The system must not attribute the difference to a specific bottleneck unless supporting evidence exists.

**Comparison workflow**

1. Verify workload identity and configuration.
2. Identify material differences between the environments.
3. Compare throughput and latency distributions.
4. Align available execution traces.
5. Compare telemetry and profiling counters.
6. Identify observations that explain or contradict candidate hypotheses.
7. Rank the remaining hypotheses.
8. Propose the smallest experiment that can distinguish between them.
9. Record the experiment result and update the diagnostic signature.

If critical workload details are missing, label the comparison inconclusive rather than presenting it as an apples-to-apples result.

**Comparison outputs**

* Baseline versus candidate performance.
* Absolute and percentage changes.
* Run-to-run variability.
* Configuration differences.
* Kernel-level changes where available.
* Telemetry changes.
* Supporting and contradictory evidence.
* Measurement limitations.
* Recommended follow-up experiments.

The objective is causal investigation, not correlation or ranking.

### Worked example: two engines on one RTX 4090

Setup. Same RTX 4090, same driver, same model (Llama-3.8B, same GGUF file, hash verified), same quantization, same prompt set, same context length, same batch size. Engine A is llama.cpp at version b4000. Engine B is vLLM at version 0.6.3. The workload fingerprint records both engine identities and versions.

Step 1, verify identity. Model hash matches. Hardware matches. The one material difference is the engine.

Step 2, identify differences. Engine A and Engine B differ in kernel selection, batching strategy, and CPU submission path. These are the candidate explanations.

Step 3, compare throughput. Engine A decodes at 82 tokens per second. Engine B decodes at 118 tokens per second. The gap is 44 percent. Run-to-run dispersion is plus or minus 3 tokens per second for both, so the gap is real.

Step 4, align traces. An nsys trace of each engine shows Engine A issues 1.4x more kernel launches per token and has longer GPU idle gaps between decode steps. Engine B uses CUDA Graphs and shows near-zero gap.

Step 5, compare telemetry. NVML shows both engines at similar power and clock. Neither is power or clock limited. Memory bandwidth is higher for Engine B but neither is near peak.

Step 6, test hypotheses. Candidate one: launch and gap overhead explains the gap. Supporting evidence: the trace correlation, the CUDA Graphs difference, the similar power and clocks. Candidate two: memory bandwidth. Contradicted, neither is near peak. Candidate three: clock or power behavior. Contradicted, both are similar.

Step 7, rank. Launch and gap overhead is the leading hypothesis. Kernel implementation differences are a secondary hypothesis the trace cannot separate without per-kernel timing.

Step 8, experiment. The smallest distinguishing experiment is to disable CUDA Graphs in Engine B and re-measure. If the gap closes, graph execution is the cause. If it persists, kernel implementation dominates.

Step 9, record. The experiment is a new fingerprint with the graph setting recorded as the changed variable. The outcome updates the diagnostic signature for this hardware and model.

### Worked example: the honest inconclusive case

Same setup, but the prompt set differs between runs. Engine A is measured on a 512-token prompt set. Engine B is measured on a 2048-token prompt set. The KV cache pressure, attention cost, and prefill time differ materially.

The comparison workflow stops at step 2. The workload identity does not match on a material variable. The output is a structured inconclusive report listing the differing variable, the reason it matters, and the smallest change that would make the comparison valid. No bottleneck claim is made.

## Optimization Engine

SMTrace should use a controlled bottleneck-elimination loop rather than an unconstrained AI tuning process.

```
Capture Workload Fingerprint
            |
            v
      Establish Baseline
            |
            v
 Identify Candidate Bottlenecks
            |
            v
 Rank Hypotheses by Evidence
            |
            v
 Select Smallest Useful Experiment
            |
            v
 Change One Variable Where Practical
            |
            v
 Run Controlled Benchmark
            |
            v
 Compare Performance and Fingerprint
            |
            v
 Is the Hypothesis Supported?
       /             \
     Yes              No
      |                |
      v                |
Record Validated    Reject or Revise
Optimization        the Hypothesis
      |                |
      v                v
Update Workload Knowledge   |
      ^                       |
      |_______________________|
```

A rejected or revised hypothesis feeds back into Identify Candidate Bottlenecks. The loop continues until the hypothesis set is exhausted or the experiment budget is spent. Retain negative results with the same care as positive ones.

**Experiment selection**

Rank experiments by:

* Expected performance benefit.
* Confidence in the underlying hypothesis.
* Cost and duration of the experiment.
* Risk of instability or disruption.
* Ability to distinguish competing hypotheses.
* Measurement quality.
* Relevance to the user's optimization objective.

An experiment that eliminates uncertainty may be more valuable than one with a larger speedup but little diagnostic value.

**Controlled changes**

Change one meaningful variable at a time where practical.

When variable interactions matter, use deliberate multi-variable or factorial experiments and retain enough metadata to explain the result.

Preserve the baseline and define rollback instructions before changing configurations.

**Objective-aware optimization**

Supported objectives should include:

* Maximum throughput.
* Minimum time to first token.
* Minimum inter-token latency.
* Maximum throughput at a specified concurrency.
* Lowest energy per operation or generated token.
* Maximum context length within a memory budget.
* Stable sustained performance within defined thermal and power limits.

Evaluate an optimization against the chosen objective, including relevant regressions.

**Negative results**

Retain unsuccessful experiments when their methodology was sound.

A result that shows no material improvement can eliminate a hypothesis, prevent repeated ineffective experiments, and improve the quality of future diagnosis.

**Sustained performance**

Separate warm-up, steady-state execution, and run-to-run variability.

A short benchmark can conceal thermal effects, power constraints, background contention, or memory pressure. SMTrace should make these conditions visible before declaring an optimization successful.

## Architecture and Data Flow

The implementation should be modular so that basic telemetry remains available when advanced profiling is unavailable.

```
                 Workload / Application
                          |
                          v
                   Benchmark Runner
                          |
             +------------+------------+
             |                         |
             v                         v
      Workload Metadata          Measurement Layer
                                       |
                         +-------------+-------------+
                         |             |             |
                         v             v             v
                    Telemetry      CUDA Tracing   HW Profiling
                    (NVML/nvidia-smi) (nsys/CUPTI)  (ncu)
                         |             |             |
                         +-------------+-------------+
                                       |
                                       v
                            Normalization / Validation
                                       |
                                       v
                              Fingerprint Store
                                       |
                         +-------------+-------------+
                         |                           |
                         v                           v
                 Differential Analysis        Diagnostic Engine
                         |                           |
                         +-------------+-------------+
                                       |
                                       v
                              Experiment Planner
                                       |
                                       v
                             Controlled Experiments
                                       |
                                       v
                             Results / Validation
                                       |
                                       v
                              Optimization Library
```

Every measurement layer is optional. Telemetry is the baseline. Attach tracing and profiling when available and permitted. The normalization layer stamps every record with its source and availability before it reaches the fingerprint store.

**Core components**

* **Workload adapters.** Integrate with selected inference engines and CUDA workloads to capture configuration and benchmark results.
* **Telemetry collectors.** Collect supported GPU, CPU, power, thermal, memory, and system metrics via NVML.
* **Tracing adapters.** Import or collect execution timelines, kernel events, synchronization events, and transfer information via Nsight Systems and CUPTI.
* **Profiling adapters.** Integrate with Nsight Compute to obtain hardware counters where permitted.
* **Fingerprint engine.** Normalize metadata and measurements into a versioned, comparable record.
* **Diagnostic engine.** Evaluate rules and hypotheses against the available evidence.
* **Experiment planner.** Generate controlled tests with explicit variables, expected outcomes, safety constraints, and rollback procedures.
* **Results engine.** Compare runs, evaluate variability, and classify optimization outcomes.
* **Local knowledge store.** Retain fingerprints, reports, experiment histories, and validated optimization profiles.
* **Optional local AI layer.** Generate hypotheses and experiment proposals from collected evidence. It must not invent missing measurements or present unsupported causal claims as facts.

## Profiling Tiers

SMTrace should support deeper levels of measurement.

**Tier 1: Always-on telemetry**

Purpose: Establish baselines and detect broad performance changes.

Collect available metrics such as:

* GPU utilization.
* VRAM allocation.
* Power and temperature.
* Clock behavior.
* CPU activity.
* End-to-end workload timing.
* Throughput and latency.

This tier should have low overhead and work without privileged kernel-level profiling.

It cannot diagnose every internal hardware bottleneck.

**Tier 2: Execution tracing**

Purpose: Explain the relationship between host activity and GPU execution.

Use supported CUDA tracing and profiling interfaces to examine:

* Kernel durations.
* Launch behavior.
* Synchronization.
* Transfers.
* CPU submission activity.
* GPU idle intervals.

This tier can distinguish some host-side overhead and execution gaps without requiring every hardware counter.

**Tier 3: Hardware counter profiling**

Purpose: Investigate kernel-level behavior and architecture-specific constraints.

Integrate NVIDIA Nsight Compute or supported profiling interfaces to obtain metrics such as:

* Occupancy and warp scheduling.
* Memory throughput.
* Cache behavior.
* Register and shared-memory usage.
* Instruction throughput.
* Supported pipeline and stall metrics.

Availability depends on the hardware, driver, profiling tool, kernel, and execution environment.

Some metrics require profiling replay, exclusive access, elevated permissions, or other constraints. Profiling may perturb execution and interfere with concurrent workloads.

The system should record collection overhead where it can be measured and distinguish profiled runs from ordinary benchmark runs.

**Metric provenance**

Every metric should carry:

* Collection source.
* Tool and version.
* Measurement interval.
* Units.
* Availability status.
* Relevant permissions or restrictions.
* Known collection overhead.
* Whether the value is measured, derived, estimated, or unavailable.

Unavailable counters must never be replaced with estimates.

A diagnosis based on basic telemetry must remain distinguishable from one supported by kernel-level evidence.

## Diagnostic Methodology

SMTrace should begin with an evidence-based rule engine.

Each diagnostic should contain:

* Observation: What was measured.
* Hypothesis: What could explain the observation.
* Supporting evidence: Which measurements support it.
* Contradictory evidence: Which observations argue against it.
* Confidence: How strongly the evidence supports the explanation.
* Alternatives: Other plausible causes.
* Experiment: How to distinguish the hypotheses.
* Success criteria: What should change if the hypothesis is correct.
* Safety constraints: What the experiment may affect.
* Outcome: Whether the hypothesis was supported, rejected, or remains unresolved.

Confidence should be based on evidence quality, measurement reliability, and the specificity of the observed behavior, not the number of metrics that correlate with a hypothesis.

For example, high power draw and high utilization do not prove compute saturation. A more specific diagnosis may require throughput measurements, execution traces, and relevant hardware counters.

**Optional local AI assistance**

A local model may help:

* Summarize traces.
* Generate candidate hypotheses.
* Explain unfamiliar profiling metrics.
* Propose controlled experiments.
* Interpret experiment results.
* Produce human-readable reports.

The model should operate on structured, provenance-bearing evidence.

It must distinguish facts from inference, preserve conflicting observations, and abstain when the available data cannot distinguish between plausible explanations.

The diagnostic engine and measurement pipeline must remain useful without AI.

## Interface Design

SMTrace should be an engineering workspace rather than a generic monitoring dashboard. The primary interface is a headless CLI and a scriptable API. A GUI is a secondary view over the same data.

### Headless CLI

The CLI is the automation surface. Every operation the GUI can perform is a CLI command. Drive experiments from scripts and CI, not clicks.

Example commands (argument shapes are illustrative; only the subcommand names are fixed):

```
# Discover the GPU and software environment
smtrace env

# Record a baseline run
smtrace run --engine llama.cpp --model llama-3.8b-q4_k_m.gguf \
  --prompt prompts/standard.json --context 4096 --repeat 5

# Compare two runs
smtrace compare baseline candidate

# Emit an exportable report
smtrace report comparison --output reports/comparison.html
```

The `smtrace compare` command is the primary differential analysis surface. It emits a structured report showing configuration differences, throughput and latency comparisons, telemetry deltas, and an inconclusive flag when material variables differ.

Experiment planning arrives with Phase 5. It will add commands that propose experiments from a fingerprint and execute them with success criteria and rollback.

### Scriptable API

A planned Python module exposes the same operations as the CLI. The API is the integration surface for inference engine plugins and custom workload adapters.

```python
from smtrace import FingerprintStore, ExperimentPlanner

store = FingerprintStore("fingerprints/")
baseline = store.load("baseline.json")
candidate = store.load("candidate.json")

report = store.diff(baseline, candidate)
print(report.inconclusive_reason)  # None when comparison is valid

planner = ExperimentPlanner(store)
plans = planner.propose(candidate)
```

### GUI screens

The GUI is a view over the fingerprint store. It is useful for interactive exploration but is not required for any workflow.

**Workload Explorer**

Browse:

* Hardware.
* Workloads.
* Models and quantizations.
* Inference engines.
* Configurations.
* Saved fingerprints.
* Historical benchmark runs.

Provide filtering and grouping by hardware, workload, engine, and relevant configuration.

**Execution Trace**

Align available events on a shared timeline:

* CPU activity.
* GPU kernels.
* Memory transfers.
* Synchronization.
* GPU idle intervals.
* Hardware telemetry.

Support selection of an event to inspect its duration, metadata, source, and relevant measurements.

**Bottleneck Analysis**

Present candidate constraints alongside the evidence supporting them.

Display:

* Observed bottleneck indicators.
* Supporting and contradictory evidence.
* Confidence and data quality.
* Missing metrics.
* Alternative explanations.
* Recommended experiments.

Users should be able to move from a diagnosis directly to the measurements that support it.

**Experiment Lab**

Provide:

* Baseline and candidate comparisons.
* Controlled configuration changes.
* Experiment histories.
* Throughput and latency comparisons.
* Memory and power trade-offs.
* Reproducibility status.
* Rollback information.
* Exportable reports.

The interface should make unsuccessful experiments as understandable as successful ones.

### Design direction

Use a technical, data-dense interface with clear hierarchy, readable trace views, and linked evidence.

Avoid decorative utilization gauges that hide measurement quality or suggest certainty where none exists.

The primary interaction should be selecting a suspected bottleneck and moving directly from the evidence to a controlled experiment.

## Proposed Data Model

A preliminary fingerprint schema could resemble the following:

```json
{
  "schema_version": 2,
  "recorded_at": "2026-10-12T12:00:00Z",
  "hardware": {
    "gpu_model": "NVIDIA RTX 4090",
    "compute_capability": "8.9",
    "architecture": "Ada Lovelace"
  },
  "software": {
    "driver_version": null,
    "cuda_runtime_version": null,
    "engine": null,
    "engine_version": null,
    "build_identifiers": null
  },
  "workload": {
    "type": "llm_inference",
    "model_hash": null,
    "quantization": null,
    "context_length": null,
    "batch_size": null,
    "gpu_offload_configuration": null
  },
  "phases": [
    {
      "phase": "prefill",
      "measurements": [
        {
          "metric": "latency",
          "unit": "milliseconds",
          "value": null,
          "samples": null,
          "run_dispersion": {
            "min": null,
            "max": null
          },
          "provenance": {
            "collection_source": null,
            "tool": null,
            "tool_version": null,
            "measurement_interval_ms": null,
            "availability": "unavailable",
            "permissions_or_restrictions": null,
            "collection_overhead": null,
            "value_status": "unavailable"
          }
        }
      ]
    },
    {
      "phase": "decode",
      "measurements": [
        {
          "metric": "throughput",
          "unit": "tokens_per_second",
          "value": null,
          "samples": null,
          "run_dispersion": {
            "min": null,
            "max": null
          },
          "provenance": {
            "collection_source": null,
            "tool": null,
            "tool_version": null,
            "measurement_interval_ms": null,
            "availability": "unavailable",
            "permissions_or_restrictions": null,
            "collection_overhead": null,
            "value_status": "unavailable"
          }
        }
      ]
    }
  ],
  "runs": {
    "count": 1
  },
  "diagnostics": {
    "hypotheses": [],
    "validated_findings": [],
    "unresolved_questions": []
  }
}
```

This is a proposed schema illustration, not an implementation contract. Define actual fields, types, and validation rules during implementation.

The schema now represents timestamps, sampling intervals, units, repeated measurements, run-to-run variability, software build identifiers, and metric availability. Production work still needs validation rules, aggregation methods, and type constraints.

The old flat keys are now generic metric names with a unit field. vram, power, and memory_bandwidth use the same record shape as the two examples. A general CUDA workload uses the same shape with its own metric and unit values.

**Design decisions**

* Per-metric provenance. Text implies this. The Metric provenance section already requires collection source, tool and version, interval, units, availability, permissions, overhead, and value status for every metric. The schema embeds a provenance object in each measurement record. The old top-level provenance block is removed.
* Phases as an array of records. Text implies this. The doc requires prefill and decode to be compared independently. The schema replaces the single phase string with an array. Each record holds a phase name and its own measurements.
* Polymorphic measurement names. Design decision. The old keys bake a unit and an LLM assumption into the name. The schema separates the metric name from the unit. An LLM decode phase uses throughput with unit tokens_per_second. A general CUDA workload uses the same record shape with a different metric and unit.
* Per-collection overhead. Text implies this. The Metric provenance section requires known collection overhead per metric. The schema moves overhead into each provenance object as collection_overhead. The old run-level profiling_overhead is removed.
* Repeated runs and dispersion. Text implies the requirement. The structure is a design decision. The production schema paragraph requires repeated measurements and variability. The schema adds runs.count and gives each measurement a samples count and a run_dispersion range. Run-to-run variability is representable.
* Timestamps and sampling intervals. Text implies this. The production schema paragraph requires both. The schema adds recorded_at at the fingerprint level and measurement_interval_ms in each provenance object.
* Software build identifiers. Text implies this. The production schema paragraph requires them. The schema adds build_identifiers to the software block.
* Metric availability. Text implies this. The production schema paragraph requires it. Each provenance object carries an availability field.
* Value status vocabulary. Text implies the distinction. The doc requires measured, derived, estimated, and unavailable to stay distinct. Each provenance object carries a value_status field with those four values. Unavailable is never replaced with an estimate.
* schema_version 2. Design decision. The structure changed enough to warrant a new version.
* Measurements as an array of records. Design decision. A flat object cannot hold per-metric provenance, samples, and dispersion. An array of records can.
* availability and value_status as separate fields. Design decision. Availability says whether the metric can be collected. Value status says how the obtained value was produced. A metric can be available and still hold a derived value.
* collection_overhead is nullable. Design decision. Overhead is recorded where it can be measured. Null means unmeasured, not zero.
* run_dispersion as a min/max range. Design decision. A range is non-parametric and easy to explain. A coefficient of variation would assume a distribution.
* Phase names are workload-defined. Design decision. Inference workloads use prefill and decode. Other CUDA workloads use their own phase names in the same record shape.

## Implementation Roadmap

**Phase 1: Workload identity and repeatable benchmarks**

* Establish the initial supported workload and inference engine.
* Discover GPU and software environment.
* Capture workload configuration.
* Separate warm-up and measured execution.
* Collect throughput, latency, and available telemetry.
* Store versioned fingerprints.
* Build baseline comparison reports.

Milestone: Repeatable benchmark results with enough metadata to explain what was tested.

**Phase 2: Differential analysis**

* Detect incompatible comparison conditions.
* Compare throughput and latency distributions.
* Identify configuration differences.
* Correlate telemetry with performance changes.
* Report uncertainty and measurement quality.
* Preserve historical results.

Milestone: Explain what changed between two comparable runs without inventing a cause.

**Phase 3: Execution tracing**

* Integrate a supported CUDA tracing workflow.
* Correlate host activity with kernel execution.
* Identify launch patterns, synchronization, transfers, and idle gaps.
* Store trace metadata.
* Compare traces across runs.

Milestone: Explain selected host-side and GPU execution bottlenecks with linked evidence.

**Phase 4: Hardware profiling**

* Integrate selected Nsight Compute workflows.
* Identify available counters for supported workloads.
* Normalize supported metrics.
* Track profiling overhead and permissions.
* Add architecture-specific diagnostic rules.

Milestone: Produce deeper kernel-level diagnoses when the required metrics are available.

**Phase 5: Controlled optimization experiments**

* Define experiment plans.
* Change one variable at a time where practical.
* Establish explicit success criteria.
* Compare performance and variability.
* Record regressions and negative results.
* Support rollback of configuration changes.
* Build a library of validated optimization profiles.

Milestone: Reproduce an improvement and explain the evidence supporting it.

**Phase 6: Local AI assistance**

* Integrate a local model endpoint.
* Generate evidence-linked hypotheses.
* Propose minimal diagnostic experiments.
* Summarize profiling results.
* Require review before changing workload configurations.
* Validate model-generated conclusions against measurements.

Milestone: Local AI accelerates investigation without becoming the source of truth for performance measurements.

**Phase 7: Architecture and workload expansion**

* Extend support beyond the initial GPU.
* Add additional inference engines.
* Develop workload-specific analysis.
* Compare hardware and engine combinations.
* Build a reusable library of diagnostic rules.

Milestone: Reuse the fingerprinting and analysis framework across additional supported hardware and workloads.

## Initial Acceptance Criteria

The first usable release should satisfy the following requirements:

* [ ] Discover and record the GPU and software environment.
* [ ] Capture a reproducible workload definition.
* [ ] Separate warm-up from benchmark measurements.
* [ ] Record repeated runs and measurement variability.
* [ ] Store versioned workload fingerprints.
* [ ] Compare two compatible runs.
* [ ] Flag material configuration differences.
* [ ] Report metric provenance and unavailable measurements.
* [ ] Avoid assigning causal explanations without supporting evidence.
* [ ] Export a benchmark report.
* [ ] Preserve the history of experiments and their outcomes.

Later milestones should add trace correlation, hardware counter analysis, controlled experiments, and optional local AI assistance.

## Technical Challenges

**Profiling permissions and availability**

Driver configuration, operating-system policy, containerization, or concurrent GPU workloads may restrict hardware profiling.

On GeForce consumer cards, Nsight Compute hardware counters require elevated permissions and may be blocked entirely by the driver. SMTrace must detect this condition and degrade gracefully.

**Measurement overhead**

Tracing, counter collection, replay passes, and synchronization can change execution behavior.

SMTrace must distinguish ordinary benchmark measurements from instrumented profiling runs.

**Reproducibility**

Performance varies with clocks, thermals, background activity, workload content, cache state, and runtime configuration.

The system must quantify variability and avoid declaring improvements that are within measurement noise.

**Metric normalization**

Different tools or versions may produce metrics that are not directly comparable.

The system should preserve raw values and provenance while defining any normalization.

**Diagnosis quality**

Multiple bottlenecks can produce similar symptoms.

The system must preserve competing hypotheses and use experiments to distinguish them.

**Architecture specificity**

A rule that works on Ada Lovelace may not apply to another architecture.

Rules must declare their supported hardware, metric requirements, and known limitations.

**Experiment safety**

Configuration changes can cause instability, consume substantial power, or interfere with active workloads.

Experiments should use explicit limits, preflight checks, reviewable changes, and recovery instructions.

## Design Principles

* Measure first: Performance claims require comparable measurements.
* Evidence over intuition: Diagnostics must link to supporting data.
* Architecture-aware: Account for hardware and workload differences.
* Reproducible: Preserve workload definitions, environments, and results.
* Controlled experiments: Prefer isolated changes and explicit success criteria.
* Honest uncertainty: Never confuse estimates with measured facts.
* Composable: Integrate existing profiling tools rather than duplicating their core functionality.
* Local-first: Keep workload data and analysis local by default.
* Human control: Require approval for consequential configuration changes.
* Incremental scope: Build reliable benchmark and comparison capabilities before adding sophisticated automated diagnosis.

## Open Decisions

These choices are implicit in the design. State them explicitly so they can be challenged or confirmed during implementation.

* **Implementation language.** Not yet chosen. Python is the pragmatic choice for the CLI, API, and NVML bindings. Performance-critical paths are thin wrappers around external tools.
* **Fingerprint storage format.** Not yet chosen. JSON files on disk are the simplest correct choice for a local-first tool. A database can come later when the file count hurts.
* **Metric sampling rate.** Not yet fixed. 100 ms is the nvidia-smi floor. The schema records the actual interval per collection rather than assuming one rate.
* **Container support.** Not yet specified. The tool should detect when it is containerized and adjust its contention and tracing expectations accordingly.
* **Non-goals.** AMD and ROCm, Windows as a primary target, datacenter GPUs, multi-GPU systems, and automated kernel generation are all out of scope for the initial release.

## Long-Term Direction

SMTrace should evolve into a reusable performance engineering system that can explain the behavior of GPU workloads across hardware, models, inference engines, and configurations.

The long-term value lies in building a growing evidence base that connects:

* Hardware and architecture.
* Workload characteristics.
* Runtime and kernel behavior.
* Performance bottlenecks.
* Diagnostic hypotheses.
* Controlled experiments.
* Validated optimizations.

Over time, SMTrace could recognize familiar workload signatures, prioritize high-value experiments, and reuse previous results to accelerate new investigations.

The objective is not to promise that every workload can be automatically optimized. It is to make performance investigation more rigorous, repeatable, and productive.

The profiler supplies measurements. SMTrace connects those measurements to hypotheses, experiments, and verified improvements.

## Project Status

The project is at concept and design stage.

Initial development should focus on workload fingerprinting, repeatable benchmarks, and trustworthy differential analysis before attempting broad automated bottleneck diagnosis.

The initial target is NVIDIA Ada Lovelace (sm_89), with local LLM inference as a practical starting workload.

## License

The license is to be determined.
