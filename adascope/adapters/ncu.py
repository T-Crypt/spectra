"""Optional ncu hardware-counter import adapter.

ncu is not installed on the test machine. This adapter imports a file an
operator produces elsewhere (CSV export or JSON). It never runs ncu and never
mutates a running process.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any


class NcuAdapter:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = str(path)

    def import_metrics(self) -> list[dict[str, Any]]:
        lower = self.path.lower()
        if lower.endswith(".json"):
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [dict(item) for item in data if isinstance(item, dict)]
            if isinstance(data, dict) and isinstance(data.get("metrics"), list):
                return [dict(item) for item in data["metrics"] if isinstance(item, dict)]
            return []
        if lower.endswith(".csv"):
            with open(self.path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                return [dict(row) for row in reader]
        return []

    def metrics_by_kernel(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for row in self.import_metrics():
            kernel = row.get("Kernel") or row.get("kernel") or row.get("name") or "unknown"
            out.setdefault(kernel, []).append(row)
        return out

    def metric_value(self, kernel: str, metric_name: str) -> float | None:
        for row in self.metrics_by_kernel().get(kernel, []):
            for key in ("Metric Value", "value", "Value"):
                metric_field = row.get("Metric Name")
                if metric_field is None:
                    metric_field = row.get("metric")
                if metric_field is None:
                    metric_field = row.get("name")
                if key in row and metric_field == metric_name:
                    try:
                        return float(row[key])
                    except (TypeError, ValueError):
                        return None
        return None
