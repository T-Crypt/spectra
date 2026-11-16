"""General CUDA workload adapter (Phase 4).

A CUDA workload that is not LLM inference can be described by a JSON file
carrying its series, the same shape ``observe`` writes. This adapter turns
that file into the domain types so the rest of the pipeline (reference,
rules, report) applies without an engine-specific path.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..model import Quality, Run, Series, Workload


def load_series(path: str | os.PathLike[str]) -> list[Series]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("series"), list):
        raise ValueError("cuda file must contain a 'series' list")
    out: list[Series] = []
    for item in data["series"]:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric", ""))
        if not metric:
            continue
        samples = item.get("samples", [])
        if not isinstance(samples, list):
            samples = []
        pairs = []
        for s in samples:
            if isinstance(s, (list, tuple)) and len(s) == 2:
                pairs.append((s[0], s[1]))
        quality = Quality(item.get("quality", "measured"))
        out.append(Series(
            metric=metric,
            unit=str(item.get("unit", "")),
            source=str(item.get("source", "cuda")),
            quality=quality,
            samples=pairs,
        ))
    return out


def build_run(path: str | os.PathLike[str], run_id: str = "cuda-run") -> Run:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("cuda file must hold a JSON object")
    hardware = data.get("hardware")
    if not isinstance(hardware, dict):
        raise ValueError("cuda file must carry a 'hardware' object")
    from ..model import HardwareProfile

    hw = HardwareProfile(**{k: v for k, v in hardware.items() if k in HardwareProfile.__dataclass_fields__})
    workload_data = data.get("workload", {})
    if not isinstance(workload_data, dict):
        workload_data = {}
    workload = Workload(
        adapter_id="cuda",
        engine_id=str(workload_data.get("engine_id", "cuda")),
        model_id=workload_data.get("model_id"),
        artifact_path=workload_data.get("artifact_path"),
        artifact_bytes=workload_data.get("artifact_bytes"),
        objective=workload_data.get("objective", {"metric": "throughput", "direction": "maximize"}),
        config=workload_data.get("config", {}),
    )
    return Run(
        id=run_id,
        started_at=str(data.get("started_at", "")),
        ended_at=str(data.get("ended_at", "")),
        hardware=hw,
        workload=workload,
        sampling=data.get("sampling", {}),
        sources=["cuda"],
        series=load_series(path),
    )
