# Contributing

Spectra targets Python 3.11+ with the standard library only in Phase 1.

## Development

```bash
python -m unittest discover -s tests
python -m build
```

## Guidelines

- Keep analysis functions pure: take data, return data, no I/O.
- Label every number as measured, derived, or hypothesis.
- Validate at boundaries (CLI, adapters, store on read); trust domain types inside.
- One variable per experiment.
- Do not mutate a running process; config changes are generated as diffs for a human to apply.

## Pull requests

Open a PR against `master`. CI must pass. No AI attribution in commits or PRs.
