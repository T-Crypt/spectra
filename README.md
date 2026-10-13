# Spectra

Architecture-aware GPU performance diagnosis and optimization.

Spectra explains why GPU workloads perform the way they do — connecting measurements to hypotheses, proposing controlled experiments, and remembering validated findings. It does not replace Nsight, nvidia-smi, or your inference engine's own metrics. Those produce numbers. Spectra explains them and keeps the explanation attached to the evidence.

## What it does

1. **Fingerprint** — Capture the hardware, software, workload, configuration, measurements, and environmental conditions needed to reproduce a performance result.
2. **Diagnose** — Correlate telemetry, traces, and hardware counters to identify candidate bottlenecks with evidence-backed confidence levels.
3. **Optimize** — Propose the smallest experiment that can confirm or reject each hypothesis, with explicit success criteria and rollback.

## Quick start

Phase 1 (the walking skeleton) observes a live inference server, writes a structured run record, and renders a correlated report.

```bash
spectra observe --target 127.0.0.1:5804 --duration 120 --hz 2
spectra report runs/<id>.json
```

See `docs/DESIGN.md` for the architecture, data model, and rule engine. See `docs/MILESTONE-1.md` for the commit-by-commit implementation plan.

## Scope

Initial target: NVIDIA Ada Lovelace (sm_89), local LLM inference workloads. The adapter and rule boundaries keep other architectures and engines addable without core changes.

## Documentation

- [DESIGN.md](docs/DESIGN.md) — Architecture, data model, rule engine, roadmap
- [VISION.md](docs/VISION.md) — Broad vision and long-term direction (consolidated from SMTrace)
- [MILESTONE-1.md](docs/MILESTONE-1.md) — Phase 1 implementation plan with acceptance tests

## Long-term direction

Build a system that learns which optimization experiments work for a specific hardware and workload combination, and keeps the evidence needed to reproduce the result. The intended outcome is less guesswork, fewer ineffective tuning changes, and a growing library of validated GPU optimization knowledge.
