"""Optional nsys trace import adapter.

nsys and ncu are not installed on the test machine, so this adapter only
imports files an operator produces elsewhere. It never runs nsys itself and
never mutates a running process. Supported inputs: CSV exports, JSON arrays,
and SQLite databases produced by ``nsys export``.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from typing import Any


class NsysAdapter:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = str(path)

    def import_events(self) -> list[dict[str, Any]]:
        lower = self.path.lower()
        if lower.endswith(".json"):
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [dict(item) for item in data if isinstance(item, dict)]
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                return [dict(item) for item in data["events"] if isinstance(item, dict)]
            return []
        if lower.endswith(".csv"):
            with open(self.path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                return [dict(row) for row in reader]
        if lower.endswith((".sqlite", ".db", ".sqlite3")):
            return self._import_sqlite()
        return []

    def _import_sqlite(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.path)
        except sqlite3.Error:
            return out
        try:
            cursor = conn.cursor()
            tables = [row[0] for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                try:
                    cols = [r[1] for r in cursor.execute(f'PRAGMA table_info("{table}")').fetchall()]
                except sqlite3.Error:
                    continue
                # Look for a table that carries a name and a duration.
                name_col = next((c for c in cols if c.lower() in ("name", "kernel", "function")), None)
                dur_col = next((c for c in cols if "dur" in c.lower() or "duration" in c.lower()), None)
                if name_col is None or dur_col is None:
                    continue
                start_col = next((c for c in cols if c.lower() in ("start", "start_ns", "ts", "timestamp")), None)
                end_col = next((c for c in cols if c.lower() in ("end", "end_ns")), None)
                select = f'"{name_col}", "{dur_col}"'
                if start_col:
                    select += f', "{start_col}"'
                if end_col:
                    select += f', "{end_col}"'
                try:
                    rows = cursor.execute(
                        f'SELECT {select} FROM "{table}"').fetchall()
                except sqlite3.Error:
                    continue
                for row in rows:
                    entry = {"name": row[0], "duration_ns": row[1], "table": table}
                    idx = 2
                    if start_col:
                        entry["start"] = row[idx]
                        idx += 1
                    if end_col:
                        entry["end"] = row[idx]
                    out.append(entry)
        finally:
            conn.close()
        return out

    def kernel_summary(self) -> list[dict[str, Any]]:
        events = self.import_events()
        summary: dict[str, dict[str, Any]] = {}
        for ev in events:
            name = ev.get("name") or ev.get("kernel") or ev.get("function") or "unknown"
            dur = ev.get("duration_ns")
            if dur is None:
                dur = ev.get("dur")
            if dur is None:
                dur = ev.get("duration")
            try:
                dur_val = float(dur)
            except (TypeError, ValueError):
                dur_val = 0.0
            entry = summary.setdefault(name, {"name": name, "count": 0, "total_ns": 0.0})
            entry["count"] += 1
            entry["total_ns"] += dur_val
        for entry in summary.values():
            entry["avg_ns"] = (entry["total_ns"] / entry["count"]) if entry["count"] else 0.0
        return sorted(summary.values(), key=lambda e: -e["total_ns"])

    def host_gaps(self, idle_threshold_ns: float = 1_000_000) -> list[dict[str, Any]]:
        """Return gaps longer than the threshold between consecutive events."""
        events = self.import_events()
        # Events must carry start/end to compute gaps; otherwise return [].
        starts = []
        for ev in events:
            s = ev.get("start")
            if s is None:
                s = ev.get("start_ns")
            if s is None:
                s = ev.get("ts")
            e = ev.get("end")
            if e is None:
                e = ev.get("end_ns")
            if s is None or e is None:
                continue
            try:
                starts.append((float(s), float(e)))
            except (TypeError, ValueError):
                continue
        starts.sort()
        gaps = []
        for (_, prev_end), (next_start, _) in zip(starts, starts[1:]):
            gap = next_start - prev_end
            if gap >= idle_threshold_ns:
                gaps.append({"start_ns": prev_end, "end_ns": next_start, "gap_ns": gap})
        return gaps


def profiling_overhead(baseline_s: float, profiled_s: float) -> float:
    """Overhead fraction: (profiled - baseline) / baseline."""
    if baseline_s <= 0:
        return 0.0
    return (profiled_s - baseline_s) / baseline_s
