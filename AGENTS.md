# Spectra - Project Rules

## Stack
- Language: Python 3.11+ (3.14 preferred)
- Dependencies: Standard library only for Phase 1. No third-party packages until Phase 2.
- Serialization: JSON / JSONL
- Testing: python -m unittest discover -s tests -- zero runtime dependencies
- Build: python -m adascope or python -m spectra (console script via pyproject.toml)

## Project structure
adascope/
  cli.py            # argparse shell, validation at the boundary
  model.py          # domain types
  store.py          # append-only run and finding store
  adapters/
    nvml.py         # NVML hardware telemetry
    lmcompat.py     # engine HTTP (lmcompat / ninfer)
  reference.py      # ReferenceModel derivations
  engine.py         # pure: observations -> ranked hypotheses
  report.py         # pure: run -> text
  analyze.py        # derive observations, rank hypotheses
  profiles/
    sm89.json       # architecture profile data
runs/               # local, gitignored
tests/

## Coding conventions
- Boundaries do validation. Parse and validate at the CLI boundary, in each adapter, and in the store on read. Trust domain types inside.
- Business logic is pure. Every analysis function takes data and returns data. No I/O, no side effects.
- Every number is labeled. measured, derived, or hypothesis. A function that cannot say which is wrong.
- Never mutate a running process. Read-only discovery first. Config changes are generated as diffs for a human to apply.
- One variable per experiment. If two keys change, the result is not attributable.
- Do not duplicate a producer. If the engine or nsys already emits it, consume it.
- The eval is the truth. A rule that cannot be shown to fire on a reproduction is a hypothesis in code.

## Testing
- python -m unittest discover -s tests must pass with no GPU and no server.
- Functional tests use fixtures, not live calls.
- Hardware tests guard with @unittest.skipUnless when no GPU is present.
- Network tests guard when the target server is unreachable.

## Git
- Commit messages: type(ref): summary -- types: feat, fix, refactor, test, docs, chore, ci, build
- Work in branches off master. One feature per branch.
- No force-push to shared branches.

## Phase 1 constraints
- No third-party dependencies.
- No native code (ctypes against libnvidia-ml.so.1 is allowed for NVML).
- No web UI.
- No auto-applying configuration changes.
- No kernel traces (Phase 3).
- No local AI assistance (Phase 4).
