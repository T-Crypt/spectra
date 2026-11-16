import json
import os
from pathlib import Path

from adascope.model import (
    Experiment,
    Finding,
    Run,
    from_dict,
    run_from_json,
    run_to_json,
    to_dict,
)


def _safe_id(run_id: str) -> str:
    """Reject ids that could escape the store root."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(f"run id must be a non-empty string, got {run_id!r}")
    if run_id in (".", "..") or "/" in run_id or "\\" in run_id:
        raise ValueError(f"run id must not contain path separators: {run_id!r}")
    if not all(c.isalnum() or c in "-_." for c in run_id):
        raise ValueError(f"run id contains unsafe characters: {run_id!r}")
    return run_id


def save_run(run: Run, root: str | Path) -> Path:
    """Atomically write a run as <root>/<run_id>.json."""
    _safe_id(run.id)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"{run.id}.json"
    tmp = root / f"{run.id}.json.tmp"
    data = run_to_json(run)
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, final)
    return final


def load_run(path: str | Path) -> Run:
    with open(path) as f:
        run = run_from_json(f.read())
    _safe_id(run.id)
    return run


def list_runs(root: str | Path) -> list[Path]:
    """List saved runs, ignoring temp files from interrupted writes."""
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.json") if not p.name.endswith(".finding.json")
                  and not p.name.endswith(".experiment.json"))


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_finding(finding: Finding, root: str | Path) -> Path:
    _safe_id(finding.id)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"{finding.id}.finding.json"
    _atomic_write(final, json.dumps(to_dict(finding), indent=2))
    return final


def load_finding(path: str | Path) -> Finding:
    with open(path) as f:
        data = json.loads(f.read())
    finding = from_dict(Finding, data)
    _safe_id(finding.id)
    return finding


def list_findings(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(root.glob("*.finding.json"))


def query_findings(
    root: str | Path,
    arch: str | None = None,
    engine_id: str | None = None,
    workload_class: str | None = None,
    variable: str | None = None,
    direction: str | None = None,
    verdict: str | None = None,
) -> list[Finding]:
    out: list[Finding] = []
    for path in list_findings(root):
        try:
            finding = load_finding(path)
        except Exception:
            continue
        if arch is not None and finding.arch != arch:
            continue
        if engine_id is not None and finding.engine_id != engine_id:
            continue
        if workload_class is not None and finding.workload_class != workload_class:
            continue
        if variable is not None and finding.variable != variable:
            continue
        if direction is not None and finding.direction != direction:
            continue
        if verdict is not None and finding.verdict.value != verdict:
            continue
        out.append(finding)
    return out


def save_experiment(experiment: Experiment, root: str | Path) -> Path:
    _safe_id(experiment.id)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"{experiment.id}.experiment.json"
    _atomic_write(final, json.dumps(to_dict(experiment), indent=2))
    return final


def load_experiment(path: str | Path) -> Experiment:
    with open(path) as f:
        data = json.loads(f.read())
    experiment = from_dict(Experiment, data)
    _safe_id(experiment.id)
    return experiment


def list_experiments(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(root.glob("*.experiment.json"))
