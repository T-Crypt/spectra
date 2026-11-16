"""Optimization library of validated profiles (Phase 4).

A validated profile is a Finding that survived an experiment, stored as a
reusable artifact keyed by (arch, engine_id, workload_class, variable,
direction). The library is a query over those findings; it never invents a
value.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import Finding, from_dict, to_dict
from .store import query_findings, save_finding


def save_profile(finding: Finding, root: str | Path) -> Path:
    """Store a validated profile (a Finding) in the library."""
    if finding.verdict.value != "confirmed":
        raise ValueError("only confirmed findings can be saved as validated profiles")
    return save_finding(finding, root)


def load_profiles(root: str | Path) -> list[Finding]:
    from .store import list_findings, load_finding

    out: list[Finding] = []
    for path in list_findings(root):
        try:
            out.append(load_finding(path))
        except Exception:
            continue
    return out


def best_profile(
    root: str | Path,
    arch: str,
    engine_id: str,
    workload_class: str,
    variable: str,
    direction: str,
) -> Finding | None:
    candidates = query_findings(root, arch=arch, engine_id=engine_id,
                               workload_class=workload_class, variable=variable,
                               direction=direction, verdict="confirmed")
    if not candidates:
        return None
    # Highest relative improvement wins.
    def improvement(f: Finding) -> float:
        delta = f.delta if isinstance(f.delta, dict) else {}
        rel = delta.get("relative")
        return float(rel) if isinstance(rel, (int, float)) else 0.0

    return max(candidates, key=improvement)
