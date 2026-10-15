# Spectra Roadmap

Phased plan combining the original SMTrace and Spectra roadmaps into a single timeline.

## Phase 1: Observe and model (Spectra Milestone 1)

The walking skeleton. One command that observes a live inference server, writes a structured run record, and renders a correlated report.

**Deliverables:**
- NVML telemetry adapter
- Engine HTTP adapter (lmcompat / ninfer)
- Append-only run store
- Memory-bound dense decode reference model
- Three diagnostic rules (sm_89)
- `spectra observe` and `spectra report` CLI commands
- Four acceptance tests (reproducibility, fidelity, reference sanity, attribution)
- Induced-bottleneck eval

**Exit criteria:** The eval ranks the seeded cause first for at least the power-cap and bandwidth-roof cases.

**Timeline:** 12 commits, see `MILESTONE-1.md`.

## Phase 2: Differential analysis and experiments

Add SMTrace's fingerprint schema, differential comparison workflow, and the controlled experiment engine.

**Deliverables:**
- Fingerprint schema v2 (SMTrace)
- Differential analysis: compare two runs, flag material differences
- Experiment engine: planned experiments, config diffs, rollback
- Finding store: persisted unit of knowledge keyed by (arch, engine, workload, delta)
- Negative results handling

**Exit criteria:** Can take two comparable runs, explain what changed, propose a controlled experiment, execute it, and store the finding.

## Phase 3: Trace correlation and hardware profiling

Add execution tracing (nsys) and hardware counter profiling (ncu) as optional tiers.

**Deliverables:**
- nsys trace import adapter
- ncu hardware counter import adapter
- Host-side and GPU execution bottleneck diagnosis
- Architecture-specific diagnostic rules for additional architectures
- Profiling overhead tracking

**Exit criteria:** Can diagnose host-side overhead and kernel-level constraints when profiling tools are available, degrades gracefully when they are not.

## Phase 4: Broader workload support

Extend beyond LLM inference to general CUDA workloads.

**Deliverables:**
- General CUDA workload adapter
- Additional inference engine adapters
- Multi-engine comparison workflows
- Optimization library of validated profiles

**Exit criteria:** Can fingerprint and diagnose a non-LLM CUDA workload (e.g., a custom kernel or GEMM benchmark).

## Phase 5: Local AI assistance

Optional local model layer for hypothesis generation and report summarization.

**Deliverables:**
- Local model integration
- Evidence-linked hypothesis drafting
- Report summarization
- Model output must never be the source of benchmark conclusions

**Exit criteria:** Assistance improves the ranking hit rate on the eval, or it is cut.

## Phase 6: GUI and explorer

Interactive exploration of the fingerprint store.

**Deliverables:**
- Workload Explorer
- Execution Trace viewer
- Bottleneck Analysis screen
- Experiment Lab

**Exit criteria:** All workflows available via CLI also available in GUI. GUI is a view over the same data.
