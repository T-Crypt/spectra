# Spectra consolidation map

How the two predecessor repositories became Spectra: what is kept, what is merged, what is
redesigned, what is parked, and what must survive before either repository is archived.

Spectra is authoritative. See the last section for the archival rule.

## Evidence convention

Every claim below carries a source: a repository, a commit, and a path.

- `AdaScope@54e799a:adascope/model.py` means the file at commit `54e799a` of `T-Crypt/AdaScope`.
- `SMTrace@e70874c:README.md` means the file at commit `e70874c` of `T-Crypt/SMTrace`.
- `Spectra@85eb33a:docs/DESIGN.md` means the committed file. Spectra's C1-C3 code is currently
  in the working tree only; see the sources table.
- "verified 2026-10-15" means a command was run on this machine during the audit and its output
  is quoted in the text.

## Sources audited

| Source | Location used | HEAD | Commits | Python LOC |
| --- | --- | --- | --- | --- |
| Spectra (authoritative) | `/home/tcrypt/projects/spectra` | `85eb33a` | 4 | C1-C3 uncommitted, 423 (package and tests) |
| T-Crypt/AdaScope | `/tmp/audit/AdaScope` | `54e799a` | 8 | 1566 (1074 package, 492 tests) |
| T-Crypt/SMTrace | `/tmp/audit/SMTrace` | `10d4889` | 14 | 117 |
| Router handoff | `/home/tcrypt/handoffs/smtrace/2026-10-10-phase1-cli` | not a git repo | n/a | 0 |

Both `/tmp/audit` clones were re-fetched during the audit; each HEAD equals its `origin/main`
tip, so neither clone is stale.

The handoff folder holds `brief.md`, `spec.md`, `01-implement.md`, `01-review.md`,
`01-pr-body.md` and `tickets/01..09`. It has no `.git` (`git rev-parse` reports "not a git
repository"), so it is a single untracked copy of that work, not a third source repository.
`/home/tcrypt/projects/SMTrace` and `/home/tcrypt/projects/AdaScope` no longer exist; the only
local copies are the clones under `/tmp` (verified 2026-10-15).

### Spectra's own state

`python -m unittest discover -s tests` reports `Ran 9 tests ... OK` (verified 2026-10-15).
Those 9 tests live in `tests/test_smoke.py` (1), `tests/test_model.py` (5) and
`tests/test_store.py` (3).

C1-C3 are green but not committed. `git ls-tree -r --name-only HEAD` at `85eb33a` lists only
`README.md`, `AGENTS.md`, `docs/*.md`, `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`
and `.ome/project.json`. `adascope/cli.py`, `adascope/model.py`, `adascope/store.py`,
`adascope/__main__.py`, `tests/test_model.py`, `tests/test_smoke.py` and `tests/test_store.py`
are untracked. `profiles/` and `runs/` are empty directories.

`adascope/adapters/`, `adascope/rules/` and `profiles/sm89.json` do not exist in Spectra
(verified by `find`). C4-C12 are not implemented: `adascope/cli.py` still prints
`spectra <command>: not implemented yet` to stderr and returns 1.

## (a) Capabilities retained

Capability, the repository that holds the best implementation, and what Spectra keeps.

| Capability | Best implementation | Evidence | Retained as |
| --- | --- | --- | --- |
| Package scaffold and test harness | AdaScope | `AdaScope@18eda67` (C1) | Spectra C1, already green |
| Domain types with JSON round-trip | Spectra (redesigned) | `Spectra:adascope/model.py` | Frozen C2 schema |
| Append-only run store | Spectra (redesigned) | `Spectra:adascope/store.py` | Frozen C3 |
| NVML telemetry over ctypes | AdaScope | `AdaScope@ed1fa3b:adascope/adapters/nvml.py` (160 LOC) | Port target for C4 |
| Engine HTTP counters and models | AdaScope | `AdaScope@ed1fa3b:adascope/adapters/lmcompat.py` (137 LOC) | Port target for C5 |
| Engine JSONL request-log reader | AdaScope | `lmcompat.py:parse_jsonl` | Port target, field names must be re-checked |
| Observe sampling loop | AdaScope | `AdaScope@ed1fa3b:adascope/observe.py` (134 LOC) | Port target for C6 |
| Memory-bound decode reference model | AdaScope | `AdaScope@ed1fa3b:adascope/reference.py` (55 LOC) | Port target for C7 |
| Arch profile data | AdaScope | `AdaScope@ed1fa3b:profiles/sm89.json` | Content retained verbatim, parked in `profiles/` |
| Rule evaluator, no `eval` | AdaScope | `AdaScope@ed1fa3b:adascope/engine.py` (59 LOC) | Port target for C8 |
| sm_89 rule set as data | AdaScope | `AdaScope@ed1fa3b:adascope/rules/sm89.json` (3 rules) | Port target for C8 |
| Observation/fact derivation and ranking | AdaScope | `AdaScope@ed1fa3b:adascope/analyze.py` (202 LOC) | Rewrite against the C2 types (see (c)) |
| Text report, pure of live sources | AdaScope | `AdaScope@ed1fa3b:adascope/report.py` (47 LOC) | Rewrite against the C2 types |
| Workload fingerprint concept | SMTrace (documentation) | `SMTrace@e70874c:README.md` "Workload Fingerprinting" | VISION.md prose; schema parked to Phase 2 |
| Differential comparison and inconclusive outcome | SMTrace (documentation) | `SMTrace@e70874c:README.md` "Differential Performance Analysis" | Parked to Phase 2 |
| Findings and negative results | SMTrace (documentation) | `SMTrace@e70874c:README.md` "Optimization Engine" | Parked to Phase 2 |
| Profiling-tier research note | SMTrace (documentation) | `SMTrace@e70874c:docs/drafts/research-profiler.md` | Parked; see `docs/RESEARCH.md` |
| CLI naming for comparison | SMTrace | `SMTrace@e70874c:src/smtrace/cli.py` (`compare`, `runs`) | Reserve the names for Phase 2 |

Schemas, interfaces and utilities retained:

- The frozen C2 types: `Quality`, `ClaimKind`, `Direction`, `HardwareProfile`, `Workload`,
  `Series`, `Run`, `Observation`, `ReferenceModel`, `Hypothesis`, `to_dict`, `from_dict`,
  `run_to_json`, `run_from_json` (`Spectra:adascope/model.py`).
- The C3 interface: `save_run(run, root)`, `load_run(path)`, `list_runs(root)`, atomic
  write to `<run_id>.json.tmp` then `os.replace`, filename `<run_id>.json`
  (`Spectra:adascope/store.py`).
- AdaScope's adapter interfaces: `Nvml.discover(device_index=0)`,
  `Nvml.sample(device_index=0)`, `LmCompat(host, port).metrics()`, `.models()`,
  `.workload(...)`, and the pure helper `parse_metrics_text(body)` (`AdaScope@ed1fa3b`).
- AdaScope's analysis interfaces: `facts_from_run`, `observations_from_run`,
  `references_from_run`, `hypotheses_from_run`, `rank` (`AdaScope@ed1fa3b:adascope/analyze.py`),
  and `evaluate`, `fires`, `load_rules`, `default_rules_path`
  (`AdaScope@ed1fa3b:adascope/engine.py`).
- AdaScope's snapshot map `THROTTLE_REASONS` with nine named bits, including
  `0x4: "sw_power_cap"`, `0x20: "sw_thermal_slowdown"`, `0x40: "hw_thermal_slowdown"`
  (`AdaScope@ed1fa3b:adascope/adapters/nvml.py`).
- AdaScope's 36 green tests as the port checklist (see (e)).

## (b) Capabilities merged

| Merged from | Into | State |
| --- | --- | --- |
| `SMTrace@e70874c:README.md` (1108 lines) as `docs/VISION.md` | `Spectra:docs/VISION.md` (140 lines) | Done in the working tree; the diff removes 1004 lines |
| SMTrace roadmap plus AdaScope/early-Spectra roadmap | `Spectra:docs/ROADMAP.md`, opening line "combining the original SMTrace and Spectra roadmaps" | Done |
| AdaScope `docs/DESIGN.md` and `docs/MILESTONE-1.md` | `Spectra:docs/DESIGN.md`, `docs/MILESTONE-1.md`, with the product name changed | Done in the working tree |
| SMTrace `AGENTS.md` plus AdaScope's implicit conventions | `Spectra:AGENTS.md` | Done |
| AdaScope README's worked reference derivation | `Spectra:docs/DESIGN.md` "Worked derivation for memory-bound dense decode" | Done, but three different numbers exist today; see (f) |

What is merged in documentation only, and still needs code: nothing. The merge of the two
visions is complete; the merge of the two implementations is the C4-C12 port.

## (c) Capabilities redesigned

These are the divergences between AdaScope's implementation and Spectra's frozen schema. Each
one is a deliberate redesign, and each one is why AdaScope's modules cannot be dropped in.

### C2 domain types (`Spectra:adascope/model.py` vs `AdaScope@808cfcb:adascope/model.py`)

| # | AdaScope | Spectra | Technical reason for the redesign |
| --- | --- | --- | --- |
| 1 | `compute_capability: tuple[int, int]` | `compute_capability: str` | It is an identity field, never arithmetic. A tuple forced a tuple-specific branch into the serializer (`_convert` in AdaScope handles `tuple` and `Union` explicitly). A string is JSON-safe with no branch. Cost: AdaScope's assertions on `(8, 9)` must be rewritten, and the string spelling (for example `"8.9"` versus `"sm_89"`) must be pinned by the adapter. |
| 2 | `class Quality(enum.Enum)`, serialized by **name** (`"MEASURED"`) | `class Quality(str, Enum)`, serialized by **value** (`"measured"`) | A `str` enum is already a JSON string; revival is `hint(value)`. Measured consequence, verified 2026-10-15 by loading a real run file written by AdaScope's own `make_run()` into Spectra's `run_from_json`: `ValueError: 'MEASURED' is not a valid Quality`. The two repos' on-disk formats are incompatible, so no AdaScope run file can be read as evidence without a converter. |
| 3 | Eleven required hardware fields | Eight optional hardware fields plus `mem_bandwidth_spec_gbps`, `pcie_link_gen`, `pcie_link_width`, `sm_count`, `l2_bytes` | NVML calls listed for C4 do not report PCIe link width, L2 size or SM count, and the reference bandwidth is documented, not measured. Those fields must come from `profiles/sm89.json`, so they cannot be required. `mem_bandwidth_measured_gbps` stays optional until a probe exists. |
| 4 | `cuda_umd_version` | `cuda_driver_version` | Names the source, not the artifact. Same value: `nvidia-smi` reports `CUDA UMD Version: 13.4` (verified 2026-10-15). This rename is the first thing that fails when Spectra reads an AdaScope run file: `TypeError: HardwareProfile.__init__() got an unexpected keyword argument 'cuda_umd_version'. Did you mean 'cuda_driver_version'?` (verified 2026-10-15). |
| 5 | `Objective` and `Constraints` dataclasses | `objective` and `constraints` plain dicts | The objective vocabulary is not frozen; Phase 1 stores one metric and two constraint keys. A dict keeps the store open without a schema bump every time a constraint is added. Cost: the type system no longer rejects a malformed objective, so validation must happen at the CLI boundary. |
| 6 | `Sampling` dataclass | `sampling: dict` | Same reason as 5. `observe` must validate `interval_ms` and `duration_s` itself. |
| 7 | `Run.to_json()` / `Run.from_json(text)` | module-level `run_to_json(run)` / `run_from_json(text)` | Keeps the domain types free of a format, and lets `store.py` own encoding. Cost: `store.py` call sites differ, and `_construct` no longer has a classmethod to recurse through. |
| 8 | `Observation.window: tuple[float, float] | str`, `Hypothesis.evidence: list[Observation]`, `alternatives: list[str]`, `confidence: str` | `Observation.window: tuple[float, float] | str`, `Hypothesis.evidence: list[str]`, `alternatives: list[Hypothesis]`, `confidence: Quality` | The frozen schema makes evidence a *reference* to observations, resolved when the report is rendered, instead of nesting copies. It also keeps `confidence` inside one enum and makes `ClaimKind` and `Direction` meaningful. Cost: AdaScope's `analyze.py` emits `Observation` objects as evidence and must be rewritten to emit ids. |
| 9 | Types defined in `analyze.py` and `reference.py` shadow the ones in `model.py` (`analyze.Observation`, `analyze.Hypothesis`, `reference.ReferenceModel`) | One definition each, in `model.py` | AdaScope has two `ReferenceModel` definitions; `analyze.py` imports the one in `reference.py`, so `model.ReferenceModel` is dead code. One definition prevents two ceilings meaning different things in one report. |

### C3 store (`Spectra:adascope/store.py` vs `AdaScope@2041c1b:adascope/store.py`)

| AdaScope | Spectra | Reason |
| --- | --- | --- |
| Public `run_path(root, run_id)` helper | Not present | One less public name; the filename rule lives in `save_run`. |
| `root.is_dir()` guard | `root.exists()` guard | Behaviour is the same for a missing root; `is_dir()` is stricter, so Spectra is marginally looser. Reverting to `is_dir()` is a one-line improvement, not a redesign. |
| `list_runs` filters `p.is_file()` | `list_runs` globs `*.json` without the filter | A directory named `x.json` would appear in Spectra's list. Low impact; noted for the port. |
| `Run.from_json(Path(path).read_text(...))` | `run_from_json(f.read())` | Follows from redesign 7. |

### Boundary-validation gap in the frozen schema (measured)

Verified 2026-10-15 with `Spectra:adascope/model.py`:

- A stored run carrying an unknown key raises `TypeError: Run.__init__() got an unexpected
  keyword argument 'unexpected_field'`.
- A stored run missing `workload` raises `TypeError: Run.__init__() missing 1 required
  positional argument: 'workload'`.

`AGENTS.md` requires validation at the store on read. A raw `TypeError` from a generated
constructor is not that. The port should add an explicit unknown-key and missing-key check in
`from_dict` that raises a domain error naming the offending field, and a test per case.

## (d) Capabilities deferred, and where they are parked

Phase numbers are `docs/ROADMAP.md` unless marked otherwise. `docs/DESIGN.md` uses a different,
four-phase numbering; where they disagree the discrepancy is listed.

| Capability | Source | Parked at |
| --- | --- | --- |
| Fingerprint schema v2 | `SMTrace@e70874c:README.md` and `docs/drafts/rewrite-data-model.md` | ROADMAP Phase 2, "Fingerprint schema v2 (SMTrace)" |
| Differential comparison of two runs, with an inconclusive outcome | SMTrace README, "Differential Performance Analysis" | ROADMAP Phase 2 |
| Finding store keyed by (arch, engine, workload, delta) | SMTrace README; AdaScope `DESIGN.md` `Finding` | ROADMAP Phase 2 |
| Negative-results handling | SMTrace README, "Negative results" | ROADMAP Phase 2 |
| Experiment engine, generated diff, rollback | SMTrace README; AdaScope `DESIGN.md` `Experiment` | ROADMAP Phase 2 |
| nsys trace import | SMTrace README "Profiling Tiers"; AdaScope `DESIGN.md` adapters | ROADMAP Phase 3 (AdaScope calls it Phase 3 too) |
| ncu hardware-counter import | Same | ROADMAP Phase 3 |
| Additional architectures and rule sets | AdaScope `DESIGN.md`; SMTrace README | ROADMAP Phase 3 |
| General CUDA workloads, extra engine adapters, multi-engine comparison | SMTrace README "Long-Term Direction" | ROADMAP Phase 4 |
| Local AI assistance | SMTrace README "Optional local AI assistance" | ROADMAP Phase 5. AdaScope `DESIGN.md` calls it Phase 4; the numbering conflicts and ROADMAP wins |
| GUI and explorer | SMTrace README "GUI screens" | ROADMAP Phase 6 |
| Contention gate before accepting a benchmark | `docs/drafts/idea-consistency.md` item 1 | ROADMAP Phase 2 (unassigned specifically). Phase 1 records `sources` but never gates |
| Warm-up and steadiness band recorded in the fingerprint | `docs/drafts/idea-consistency.md` item 2 | ROADMAP Phase 2 |
| Energy per objective | `docs/drafts/idea-consistency.md` item 4 | ROADMAP Phase 4 ("beyond LLM inference" is the closest slot) |
| Experiment preflight and safety envelope | `docs/drafts/idea-consistency.md` item 5 | ROADMAP Phase 2, with the experiment engine |
| Measured bandwidth probe (`mem_bandwidth_measured_gbps`) | AdaScope `model.py` field, always `None` | Not scheduled. AdaScope `DESIGN.md` says "add a probe only when a measured bandwidth number is worth the build cost" |

## (e) Tests and historical experiments preserved

AdaScope reports `Ran 36 tests ... OK (skipped=1)` (verified 2026-10-15). The single skip is the
whole `tests/test_lmcompat.py` module, because `127.0.0.1:5804` is down. `tests/test_nvml.py`
ran and passed, which proves the NVML path works while another process holds the card.

Ten test modules, not eleven: `tests/` holds 10 `test_*.py` files plus an empty `__init__.py`.

| AdaScope module | Tests | Verdict for the port | Why |
| --- | --- | --- | --- |
| `tests/test_scaffold.py` | 2 | Port with one edit | Asserts `adascope.__version__ == "0.1.0"`. Spectra's `adascope/__init__.py` is 0 bytes, so the attribute does not exist. Either drop the assertion or add `__version__`. |
| `tests/test_model.py` | 7 | Rewrite | Builds `Objective`, `Constraints`, `Sampling`, `compute_capability=(8, 9)` and asserts name-serialized enums (`"MAXIMIZE"`, `"MEASURED"`). All five of those are redesigned or removed. It is also the shared fixture provider for three other modules (see (h)). |
| `tests/test_store.py` | 6 | Port, with the fixture import moved | Assertions match Spectra's store semantics: save then load, idempotent resave with identical bytes, `.tmp` ignored, sorted listing, missing root empty. |
| `tests/test_nvml.py` | 3 | Rewrite the profile expectations, keep the checks | `compute_capability == (8, 9)` becomes whatever string spelling C4 pins; `power_limit_w`, `clock_sm_max_mhz`, `vram_total_bytes` and the `nvidia-smi` cross-check survive unchanged. Must keep its `@unittest.skipUnless` guard. |
| `tests/test_lmcompat.py` | 3 | Split | `parse_metrics_text` tests are pure and port unchanged. The two live tests must stay guarded and must not build a `Workload` through the redesigned types. |
| `tests/test_reference.py` | 3 | Port unchanged | Depends only on `dense_decode_reference`, `Quality` and `profiles/sm89.json`, none of which change. The file `profiles/sm89.json` is missing from Spectra and must be added for this test to run. |
| `tests/test_engine.py` | 5 | Port unchanged | Same evaluator semantics. Must stop using the CWD-relative path `adascope/rules/sm89.json` and use `default_rules_path()`; the rules file is missing from Spectra. |
| `tests/test_analyze.py` | 3 | Rewrite | `fixture_run()` is reusable verbatim, but assertions on `Hypothesis.rules` and the shape of `evidence` follow the redesigned types. |
| `tests/test_report.py` | 2 | Rewrite | Pins the render contract, which changes because `objective` is now a dict. |
| `tests/test_cli_observe.py` | 4 | Rewrite and split | Two tests are pure argument parsing; two need a live server and a GPU. The rewrite should also stop hardcoding `/home/tcrypt/ninfer-4090/models/qwen3_8_27b.ninfer` and `18210531328` in the test body. |

SMTrace's `tests/test_cli.py` (7 tests) is **not portable as written**, for three reasons:

1. It is pytest, and Phase 1 forbids third-party dependencies.
2. It asserts exit code 2 and the exact message `not yet implemented (ticket 02)`. Spectra's shell
   returns 1 and prints `spectra <command>: not implemented yet`.
3. As committed it needs an editable install: `python -m pytest tests -q` on a bare clone gives
   `7 failed ... assert 1 == 2` (verified 2026-10-15), because `python -m smtrace.cli` cannot
   import the `src`-layout package. With `PYTHONPATH=src` the same command gives `7 passed`.

Recommendation: keep two of its ideas as new unittest cases in Spectra -- `--help` lists the
subcommands, and an unwired subcommand exits non-zero with a message -- and drop the ticket ids.
The other five are restatements of those two.

Spectra's existing 9 tests are retained as they are: `tests/test_smoke.py`,
`tests/test_model.py` (round trip, tuple samples, enum values, `Observation`/`ReferenceModel`
round trip, `ClaimKind`), `tests/test_store.py` (save/load, idempotent resave, `.tmp` ignored).

One naming defect, not a behaviour defect: `tests/test_model.py::test_enums_serialize_by_name`
asserts `"maximize"` and `"measured"`, which are enum **values**. The test asserts the right
thing under a stale name.

## (f) Duplication and conceptual overlap

| Overlap | Contenders | Winner | Note |
| --- | --- | --- | --- |
| Product vision | `SMTrace@e70874c:README.md` (1108 lines) vs `AdaScope@5bc8353:docs/DESIGN.md` | Spectra's `docs/VISION.md` + `DESIGN.md` split | SMTrace's breadth plus AdaScope's specificity; the merge is done |
| Roadmaps | SMTrace README "Implementation Roadmap" (7 phases) vs AdaScope `DESIGN.md` "Roadmap" (4 phases) | `docs/ROADMAP.md` (6 phases) | Neither original survives; the two numberings still disagree on where local AI sits |
| Milestone 1 plan | `AdaScope@5bc8353:docs/MILESTONE-1.md` vs `Spectra:docs/MILESTONE-1.md` | Spectra's | Same text; Spectra's names the `spectra` CLI and the redesigned `cuda_driver_version` |
| CLI surface | SMTrace `env, workloads, run, compare, report, runs` vs Spectra `observe, report` | Spectra's for Phase 1 | SMTrace's `compare` and `runs` are the natural Phase 2 spelling; reserve them |
| GPU telemetry | AdaScope NVML ctypes adapter vs SMTrace's plan to shell out to `nvidia-smi` | AdaScope's NVML adapter | NVML returns throttle bits and clocks in one call; parsing `nvidia-smi` text loses the named bits. `nvidia-smi` remains only as a cross-check in the test |
| GPU gauges over HTTP | `llama-swap` `/metrics` at `127.0.0.1:9090` | Not Spectra's job | Verified live 2026-10-15: 16 gauge names including `llamaswap_gpu_power_draw_watts`, `llamaswap_gpu_memory_used_bytes`, `llamaswap_gpu_temperature_celsius`. Spectra consumes NVML directly for the richer fields, and must not duplicate a producer it does not need. Note this endpoint carries no token counters |
| The reference ceiling number | `AdaScope@54e799a:README.md` about `1008 / 17 = 59` tok/s; `docs/DESIGN.md` about 59 tok/s; `docs/MILESTONE-1.md` 55.4 tok/s | The exact-artifact value, 55.4 tok/s | Not a modelling disagreement: 1008e9 / 18210531328 = 55.353 tok/s, while 1008/17 = 59.29 uses a rounded 17 GB. The docs should carry one number, pinned to the exact artifact bytes, and say which input is rounded |
| The speculative factor | `docs/MILESTONE-1.md` says 1.97; `AdaScope@ed1fa3b:analyze.py` computes 1 + accepted/drafted, which from the milestone's own counters is 1 + 43693/65850 = 1.6635 | Unresolved. This is a real disagreement, not rounding | 55.353 * 1.6635 = 92.08 tok/s, below the recorded 109.1 tok/s, so `objective_ratio` would be 1.185 and the bandwidth-roof rule would fire above its own ceiling. The 1.97 figure is 109.1 / 55.353, i.e. derived from the rate it is meant to predict. `docs/EVAL.md` makes settling this the first experiment |
| `ReferenceModel` type | `model.py` and `reference.py` in AdaScope | One definition in `model.py` | See (c) row 9 |
| `Observation`/`Hypothesis` types | `model.py` and `analyze.py` in AdaScope | One definition in `model.py` | Same class of defect |
| Contention detection | SMTrace's `--query-compute-apps` gate (documentation) vs a `sources` list in the run | The gate, when it exists | Today's state makes the case: pid 1293313 holds 17023 MiB of 24564 MiB (verified 2026-10-15). Phase 1 records the run without gating it |

## (g) Features that exist only in documentation

Honesty first: everything in this section has **no passing test anywhere**, in either repository.

SMTrace (all in `SMTrace@e70874c`):

- Fingerprint schema v2 and its 17 design decisions (`README.md` "Proposed Data Model",
  `docs/drafts/rewrite-data-model.md`). The schema is an illustration; the doc says so.
- Differential comparison, comparison workflow steps 1-9, comparison outputs, and the honest
  inconclusive case (`README.md` "Differential Performance Analysis").
- The two worked examples. The engine A versus engine B numbers (82 and 118 tokens per second,
  a 44 percent gap) are an illustration, not a measurement; no run records back them.
- Optimization engine, experiment selection criteria, objective-aware optimization, negative
  results, sustained performance (`README.md` "Optimization Engine").
- Profiling tiers 1-3 and per-metric provenance (`README.md` "Profiling Tiers").
- Diagnostic methodology's ten-element diagnosis (`README.md` "Diagnostic Methodology").
- Scriptable API surface (`FingerprintStore`, `ExperimentPlanner`) and four GUI screens
  (`README.md` "Interface Design"). No code.
- The four capability additions and the open decisions in `docs/drafts/idea-consistency.md`,
  including the contention gate, the steadiness band, the fingerprint diff as a structured
  report, energy per objective, and the experiment preflight.
- The 341-line interface rewrite in `docs/drafts/rewrite-interface-diagrams.md`, which is a
  rewrite plan for a README, not a design for code.
- The router handoff `spec.md` plus 9 tickets in
  `/home/tcrypt/handoffs/smtrace/2026-10-10-phase1-cli`, which plan Phase 1 in detail and
  produced only `src/smtrace/cli.py` and `tests/test_cli.py`.

AdaScope (design text with no code, at `54e799a`):

- `Experiment` and `Finding`, and the whole library-over-findings idea (`docs/DESIGN.md`).
- The `Adapter`, `nsys(Adapter)` and `ncu(Adapter)` protocols. No file named `nsys.py` or
  `ncu.py` exists.
- `ArchitectureProfile` as a versioned artefact with `throttle_semantics` and `citations`.
  `profiles/sm89.json` carries the keys; no code reads anything but `mem_bandwidth_spec_gbps`
  (verified by grep in `analyze.py`).
- `mem_bandwidth_measured_gbps`, `pcie_link_gen`, `pcie_link_width`, `sm_count`, `l2_bytes`:
  present in the type, populated in the profile file, consumed by nothing.
- A second and third rule set for another architecture. Only sm_89 exists.
- `docs/README.v0.md` (209 lines) and `docs/STATUS.md` (session state at commit `983290d`).
- The four acceptance tests and the induced-bottleneck eval, which are planned in
  `docs/MILESTONE-1.md` as C11 and C12 and have no file.

## (h) Unnecessary coupling, and what to do instead

| Coupling in the predecessor code | Why it hurts | Do instead |
| --- | --- | --- |
| `AdaScope:report.py` reads `workload.objective.metric` and `.direction.value` | Breaks against the frozen dict shape and scatters schema knowledge into the renderer | One accessor in the model module, or validate the dict at the CLI boundary and let the renderer take a small view object |
| `AdaScope:observe.py` wraps NVML and the engine in bare `except Exception` and still records `sources=["nvml"]` when a call failed | A dead adapter is indistinguishable from a quiet one, and the run claims a source it does not have | Record a source only when it produced at least one sample, and report the failure at the CLI boundary |
| `AdaScope:engine.py` and its tests load `adascope/rules/sm89.json` and `profiles/sm89.json` by CWD-relative path | Tests fail from any other directory, and the rule set is not found after installation | `default_rules_path()` already resolves from `__file__`; use it, and add the same helper for the profile |
| `AdaScope:tests/test_store.py` and `tests/test_report.py` import `make_run` from `tests.test_model`, and `test_report.py` imports `fixture_run` from `tests.test_analyze` | A fixture edit in one module breaks unittest discovery for unrelated modules | One `tests/support.py` (or `tests/fixtures/`) that every test imports |
| `AdaScope:analyze.py` picks evidence by `rule["id"].endswith("power-cap-limit")` | Couples the analyser to specific rule ids, so a second architecture's rule file silently gets another architecture's evidence | Let each rule declare `evidence_metrics` in its JSON. Rules are data; the analyser should not know names |
| `AdaScope:lmcompat.py` `parse_metrics_text` adds a stripped alias for every name | Two keys for one number invites a caller to sum both; the `setdefault` then assignment pair is also dead weight | Return one map keyed by the full name, and add the alias only if a caller needs it, in the adapter |
| `AdaScope:adapters/nvml.py` calls `lib.nvmlInit_v2()` and `nvmlShutdown()` on every `sample()` | A hot sampling loop re-initialises the library every tick | Initialise once per adapter instance and shut down explicitly |
| Spectra `model.py` `_construct` passes unknown or missing keys straight into the constructor | Produces a `TypeError` from generated code instead of a domain error, at a boundary the rules say must validate | Validate key sets in `from_dict` and raise a domain error that names the field |
| `AdaScope:tests/test_cli_observe.py` hardcodes the artifact path and byte count | The test cannot run anywhere but this machine, without saying so | Put machine facts in one `tests/fixtures/machine.py` and skip when the path is absent |

Two environment claims that no longer hold, both load-bearing in the docs:

- `docs/DESIGN.md` says "The test machine has Python 3.14 and no numpy". Python is 3.14.8 and
  numpy 2.5.4 is installed (verified 2026-10-15). The stdlib-only rule still stands as a project
  decision, but the justification is stale. Same for the `docs/MILESTONE-1.md` claim that
  Nsight is not installed: still true, `command -v ncu nsys` finds neither.
- `pyproject.toml` names `build-backend = "setuptools.backends._legacy:_Backend"`. That module is not part of
  setuptools 84.0.0, so building the package cannot work: `python -c "import setuptools.backends._legacy"`
  fails with `ModuleNotFoundError: No module named 'setuptools.backends'` (verified 2026-10-15).
  `setuptools.build_meta` is the usual value.

## (i) Experimental work in one repo and not the other

AdaScope only:

- The NVML ctypes binding and the nine named throttle bits, with a live cross-check against
  `nvidia-smi`.
- Prometheus text parsing with prefix stripping, and a JSONL `server_start` / `request_done`
  reader.
- The sampling loop that turns adapter ticks into `Series`, including boolean throttle series.
- The `bytes_per_forward` reference derivation and the 1008 GB/s to 55.4 tok/s result, which is
  the one place in either repo where a number is derived from first principles and checked.
- The rule evaluator with no `eval`, and the three sm_89 rules as data.
- `rank()` with a documented confidence weight and deterministic tie-breaking.
- The text renderer, and the idea that rendering is a pure function of a stored run.
- 36 green tests, and the per-commit verification discipline in `docs/MILESTONE-1.md`.

SMTrace only:

- The fingerprint as a first-class unit, with per-metric provenance and an explicit
  `value_status` vocabulary that keeps `unavailable` distinct from an estimate.
- Differential comparison as the primary workflow, and "inconclusive" as a first-class output
  rather than an error.
- Findings, and the rule that negative results are retained.
- Experiment selection ranked by ability to distinguish hypotheses rather than by expected gain.
- The tier model that degrades from telemetry to tracing to counters.
- The profiling research note with per-claim sourcing.
- A CLI that names comparison and run listing from the start.

Neither repo has, in any form: a stored fingerprint, a two-run comparison, an experiment runner,
a findings store, an nsys or ncu import path, or a single cross-run result.

## (j) Migration plan and archival

### What must be preserved before either repository is archived

AdaScope:

- Merge `54e799a211d4b5c97c8923d607a09df98f13d18e` and its parent `ed1fa3b4757670fe7a50bc51a24a12db492a9513` on branch `feat/demo-c4-c10`. That tree is the only copy of C4-C10 and the source for the port.
- The C1-C3 commits `18eda67`, `808cfcb`, `2041c1b`, which Spectra's C1-C3 mirror, plus the design commits `5bc8353` and `983290d`.
- `adascope/adapters/nvml.py`, `adapters/lmcompat.py`, `observe.py`, `reference.py`, `engine.py`, `analyze.py`, `report.py` byte for byte.
- `adascope/rules/sm89.json` and `profiles/sm89.json` byte for byte. The profile's values were read for this document: `mem_bandwidth_spec_gbps` 1008, `sm_count` 128, `l2_bytes` 75497472, `pcie_link_gen` 4, `pcie_link_width` 16, `clock_sm_max_mhz` 3135, `clock_mem_max_mhz` 10501.
- `docs/STATUS.md`, which records the 15-test C1-C3 pause and the resume order. It is the only record of how the work was sequenced.
- The 36-test suite, as the port checklist in (e).

SMTrace:

- `README.md` at `e70874c`, which carries the fingerprint schema, the CLI surface and the worked examples. It is the only surviving statement of SMTrace's design intent.
- The four drafts at `e70874c`: `docs/drafts/idea-consistency.md` (79 lines),
  `docs/drafts/research-profiler.md` (95), `docs/drafts/rewrite-data-model.md` (128),
  `docs/drafts/rewrite-interface-diagrams.md` (341).
- The six-subcommand CLI surface and its ticket map in `src/smtrace/cli.py`.
- The router handoff folder `/home/tcrypt/handoffs/smtrace/2026-10-10-phase1-cli`, which is not
  in git at all. Its `spec.md`, `brief.md` and `tickets/01..09` are the most detailed plan
  either predecessor produced. Copy it somewhere durable before the archive.

Neither repository:

- No history is deleted, rewritten, force-pushed or squashed. Archiving means making a
  repository read-only, not losing it.
- No experiment is overwritten. A branch that produced a result -- including a result that
  failed -- stays readable at its own commit.

### What does not need preserving

- `.ome/` project state in either repo, including SMTrace's committed board skill at `33b8768`,
  which `eba3af4` already removed.
- `__pycache__` directories, which are checked in to neither repo but exist in both clones.
- SMTrace's `pytest==9.1.1` and `ruff==0.17.0` pinning (`5165d32`) and its CI workflow. Spectra
  has its own CI and its own rule of zero runtime dependencies.
- SMTrace's `src/smtrace/cli.py` dispatch itself, and SMTrace's `tests/test_cli.py`, which fails
  on a bare clone. Keep both in history; port at most two of the ideas.
- AdaScope's duplicate type definitions (`reference.ReferenceModel`, `analyze.Observation`,
  `analyze.Hypothesis`) and its six shadowed store behaviours, once the port is verified.

### The rule

1. Spectra is authoritative. It is the only repository that receives new measurement or
   diagnostic capability.
2. Parallel development of the same measurement or diagnostic capability stops. Any open branch
   in SMTrace or AdaScope that adds an adapter, a reference model, a rule, an analysis function
   or a report renderer is either closed or ported into Spectra, not merged upstream.
3. Before either repository is archived, tag its tip so the preserved commits are addressable
   by name: `git -C <clone> tag -a spectra-consolidated-2026-10-15 -m "superseded by Spectra"`.
   Pushing the tag is a decision for the owner; the local tag alone makes the history
   addressable in the clone that exists.
4. Archive, do not delete. `/home/tcrypt/projects/SMTrace` and `/home/tcrypt/projects/AdaScope`
   are already gone from this machine; the only local copies are the `/tmp/audit` clones.
   `/tmp` is not durable. Re-clone both to a durable path, or push the preserve list above into
   Spectra's `docs/`, before the source is treated as archived.

### Live evidence for the migration

Adascope's C4-C10 tree was cloned and run during this audit: `Ran 36 tests ... OK (skipped=1)`.
The port target is not theoretical. It is green on this machine, today, except for the one test
that needs the engine at `127.0.0.1:5804`, which is down.
