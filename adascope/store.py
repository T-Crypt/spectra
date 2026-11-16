import os
from pathlib import Path

from adascope.model import Run, run_from_json, run_to_json


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
    return sorted(root.glob("*.json"))
