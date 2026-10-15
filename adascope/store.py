import os
from pathlib import Path

from adascope.model import Run, run_from_json, run_to_json


def save_run(run: Run, root: str | Path) -> Path:
    """Atomically write a run as <root>/<run_id>.json."""
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
        return run_from_json(f.read())


def list_runs(root: str | Path) -> list[Path]:
    """List saved runs, ignoring temp files from interrupted writes."""
    root = Path(root)
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))
