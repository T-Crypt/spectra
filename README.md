<p align="center">
    <img src="assets/banner.png" alt="Spectra" width="100%">
</p>

<p align="center">
    <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB?logo=python&logoColor=white" alt="Python 3.11 or newer"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>
    <a href="https://github.com/T-Crypt/spectra/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/T-Crypt/spectra/ci.yml?branch=master&label=ci" alt="CI status"></a>
    <img src="https://img.shields.io/badge/tests-76%20passing-brightgreen" alt="76 tests passing">
</p>

<p align="center">
    <a href="#what-it-is">What it is</a> ·
    <a href="#quick-start">Quick start</a> ·
    <a href="#what-it-does">What it does</a> ·
    <a href="#scope">Scope</a> ·
    <a href="#documentation">Documentation</a>
</p>

---

# Spectra

Spectra explains why GPU workloads perform the way they do. It connects measurements to hypotheses, proposes controlled experiments, and keeps the explanation attached to the evidence. It does not replace Nsight, nvidia-smi, or your inference engine's own metrics. Those produce numbers. Spectra explains them.

```bash
spectra observe --target 127.0.0.1:5804 --duration 120 --hz 2
spectra report runs/<id>.json
```

## What it is

Phase 1 is a walking skeleton. It observes a live inference server, writes a structured run record, and renders a correlated report. Every number in the report is labeled measured, derived, or hypothesis.

## What it does

| Step | What happens |
| --- | --- |
| Fingerprint | Capture hardware, software, workload, configuration, measurements, and environmental conditions needed to reproduce a performance result. |
| Diagnose | Correlate telemetry, traces, and hardware counters to identify candidate bottlenecks with evidence-backed confidence levels. |
| Optimize | Propose the smallest experiment that can confirm or reject each hypothesis, with explicit success criteria and rollback. |

## Quick start

Install from source:

```bash
pip install .
```

Observe a live server:

```bash
spectra observe --target 127.0.0.1:5804 --duration 120 --hz 2
spectra report runs/<id>.json
```

Or drive the workload yourself, so the run carries it:

```bash
spectra bench --target 127.0.0.1:5804 --duration 120 --hz 2 --prompt-words 256 --completion-tokens 256 --concurrency 1
spectra report runs/<id>.json
```

Run the tests. No GPU or server is needed:

```bash
python -m unittest discover -s tests
```

## Scope

Initial target: NVIDIA Ada Lovelace (sm_89), local LLM inference. Engine name tables cover ninfer, llama.cpp and vLLM; `--engine` forces one, and auto-detection reads a single `/metrics` fetch. Adapters and rule boundaries keep other architectures and engines addable without core changes. Phase 1 uses the standard library only.

## Status

76 unit tests pass. 8 skip without GPU, engine, or opt-in. The recorded-counter check passes at 109.1 tok/s, factor 3.02, ceiling 167.1, ratio 0.65.

One 60 s loaded run against the live backend gave 104.6 tok/s over 45 requests at 427 W mean against the 450 W limit. No rule fired. Power sat at 0.95 of the limit while the ratio sat at 0.77, below both firing bands.

The control stage has not passed yet. Ten repetitions came back inconclusive. The backend unloads 5 minutes after load while a stage needs 10 or more, so later repetitions lose the engine. Eval runs need a longer unload timeout. The treatment stage needs `nvidia-smi -pl`, which needs a password this setup lacks, so it records inconclusive.

This engine build exposes no `/metrics`, so counter series are absent and the request log carries the rate and the spec factor. The counter path wins whenever counters exist.

## Documentation

- [DESIGN.md](docs/DESIGN.md): architecture, data model, rule engine
- [VISION.md](docs/VISION.md): broad vision and long-term direction
- [MILESTONE-1.md](docs/MILESTONE-1.md): Phase 1 implementation plan with acceptance tests
- [CONSOLIDATION.md](docs/CONSOLIDATION.md): what SMTrace and AdaScope contribute
- [RESEARCH.md](docs/RESEARCH.md): prior art and the remaining contribution
- [EVAL.md](docs/EVAL.md): falsifiable evaluation design
- [ROADMAP.md](docs/ROADMAP.md): phases 1 to 6

## Long-term direction

Build a system that learns which optimization experiments work for a specific hardware and workload combination, and keeps the evidence needed to reproduce the result. The intended outcome is less guesswork, fewer ineffective tuning changes, and a growing library of validated GPU optimization knowledge.
