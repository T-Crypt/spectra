"""Observe command: sample live adapters and store a raw Run.

The store holds raw measurements only. Analysis runs later, at report time,
as a pure function of the stored file.

Failure honesty: a source is listed only when it produced at least one sample,
and a run with no hardware samples is not stored at all. A dead adapter must
not be indistinguishable from a quiet one.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .adapters.engines import ENGINE_IDS, canonical_name, detect_engine
from .adapters.lmcompat import LmCompat, parse_jsonl
from .adapters.nvml import Nvml
from .model import Quality, Run, Series
from .store import save_run

JSONL_SOURCE = "lmcompat:jsonl"


def parse_target(target: str) -> tuple[str, int]:
    host, sep, port_text = target.rpartition(":")
    if not sep or not host or not port_text.isdigit():
        raise ValueError(f"target must be HOST:PORT, got {target!r}")
    if any(ch in host for ch in "/?# \t\r\n"):
        raise ValueError(f"host contains unsafe characters in target {target!r}")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError(f"port out of range in target {target!r}")
    return host, port


def parse_sampling(duration_s: float, hz: float) -> dict:
    """Validate the two sampling numbers before any I/O happens."""
    duration_s = float(duration_s)
    hz = float(hz)
    if not duration_s > 0:
        raise ValueError(f"duration must be positive, got {duration_s}")
    if not hz > 0:
        raise ValueError(f"hz must be positive, got {hz}")
    interval_ms = int(1000 / hz)
    if interval_ms < 1:
        raise ValueError(f"hz {hz} is more than 1000 samples per second")
    return {"interval_ms": interval_ms, "duration_s": duration_s}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hardware_unit(metric: str) -> str:
    if metric.endswith("_w"):
        return "W"
    if metric == "temp_c":
        return "C"
    if metric.endswith("_mhz"):
        return "MHz"
    if metric.endswith("_pct"):
        return "%"
    if metric.endswith("_bytes"):
        return "bytes"
    return ""


def _engine_unit(metric: str) -> str:
    if metric.endswith("_seconds_total"):
        return "s"
    if metric.endswith("_total"):
        return "count"
    return ""


def _request_series(summary, start_ms: int, end_ms: int) -> list[Series]:
    """Per-request decode series for the instance and window just observed.

    The request log is append-mode across restarts, so only records carrying
    the current ``server_instance_id`` and a timestamp inside the sample window
    are kept. Each series is cumulative, so the steady-window delta is the
    token-weighted aggregate over the requests in that window.
    """
    instance_id = summary.server_instance_id
    kept = [
        request
        for request in summary.requests
        if request.timestamp_unix_ms is not None
        and start_ms <= request.timestamp_unix_ms <= end_ms
        and (instance_id is None or request.server_instance_id in (None, instance_id))
    ]
    if not kept:
        return []
    tokens: list[tuple[float, float]] = []
    seconds: list[tuple[float, float]] = []
    rounds: list[tuple[float, float]] = []
    total_tokens = 0
    total_seconds = 0.0
    total_rounds = 0
    for request in kept:
        # The first token of a request comes from the prefill pass, which is
        # the engine's own convention for a decode rate. See the engine's
        # request_log and operational log.
        total_tokens += max(0, request.completion_tokens - 1)
        total_seconds += request.decode_seconds
        total_rounds += request.rounds or 0
        offset = (request.timestamp_unix_ms - start_ms) / 1000.0
        tokens.append((offset, float(total_tokens)))
        seconds.append((offset, float(total_seconds)))
        rounds.append((offset, float(total_rounds)))
    return [
        Series(metric="request_decode_tokens", unit="count", source=JSONL_SOURCE,
               quality=Quality.MEASURED, samples=tokens),
        Series(metric="request_decode_seconds", unit="s", source=JSONL_SOURCE,
               quality=Quality.MEASURED, samples=seconds),
        Series(metric="request_decode_rounds", unit="count", source=JSONL_SOURCE,
               quality=Quality.MEASURED, samples=rounds),
    ]


def observe(
    target: str,
    duration_s: float = 30.0,
    hz: float = 2.0,
    artifact_path: str = "",
    config: dict | None = None,
    jsonl_path: str | None = None,
    out: str | Path = "runs",
    config_file: str | None = None,
    engine: str = "auto",
) -> Path:
    """Sample NVML and the engine for duration_s and store one Run."""
    host, port = parse_target(target)
    sampling = parse_sampling(duration_s, hz)
    interval = sampling["interval_ms"] / 1000.0
    duration_s = sampling["duration_s"]

    if engine != "auto" and engine not in ENGINE_IDS:
        raise ValueError(f"unknown engine {engine!r}; expected auto or one of {', '.join(ENGINE_IDS)}")

    merged_config: dict = dict(config or {})
    if config_file:
        raw = json.loads(Path(config_file).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config file must hold a JSON object")
        merged_config.update({str(k): v for k, v in raw.items()})

    hardware = Nvml.discover()
    client = LmCompat(host, port)
    try:
        models = client.models()
        model_id = str(models[0].get("id", "unknown")) if models else "unknown"
    except Exception:
        model_id = "unknown"
    if engine == "auto":
        # One fetch decides the name table. A dead /metrics leaves the
        # detection at its default and the loop keeps trying, so an engine
        # that answers late still gets observed.
        try:
            probe = set(client.metrics())
        except Exception:
            probe = set()
        engine_id, _basis = detect_engine(probe)
    else:
        engine_id = engine
    workload = client.workload(model_id, merged_config, artifact_path, jsonl_path,
                               engine_id=engine_id)

    count = max(1, round(duration_s * hz))
    hw_accum: dict[str, list[tuple[float, float]]] = {}
    eng_accum: dict[str, list[tuple[float, float]]] = {}
    hw_samples = 0
    eng_samples = 0
    hw_failure: str | None = None
    started = _utc_now()
    wall_start = time.monotonic()
    start_ms = int(time.time() * 1000)
    for i in range(count):
        tick_start = time.monotonic()
        elapsed = tick_start - wall_start
        try:
            sample = Nvml.sample()
        except Exception as exc:
            sample = {}
            hw_failure = str(exc)
        if sample:
            hw_samples += 1
        for key, value in sample.items():
            if isinstance(value, bool):
                point = (elapsed, 1.0 if value else 0.0)
            elif isinstance(value, (int, float)):
                point = (elapsed, float(value))
            else:
                continue
            hw_accum.setdefault(key, []).append(point)
        try:
            metrics = client.metrics()
            eng_samples += 1
        except Exception:
            metrics = {}
        for key, value in metrics.items():
            eng_accum.setdefault(canonical_name(engine_id, key), []).append((elapsed, float(value)))
        wait = interval - (time.monotonic() - tick_start)
        if wait > 0 and i < count - 1:
            time.sleep(wait)
    end_ms = int(time.time() * 1000)
    ended = _utc_now()

    if hw_samples == 0:
        raise RuntimeError(f"NVML produced no samples: {hw_failure or 'unknown error'}")

    series = [
        Series(metric=key, unit=_hardware_unit(key), source="nvml",
               quality=Quality.MEASURED, samples=hw_accum[key])
        for key in sorted(hw_accum)
    ]
    series.extend(
        Series(metric=key, unit=_engine_unit(key), source="lmcompat",
               quality=Quality.MEASURED, samples=eng_accum[key])
        for key in sorted(eng_accum)
    )

    request_series: list[Series] = []
    if jsonl_path and os.path.isfile(jsonl_path):
        request_series = _request_series(parse_jsonl(jsonl_path), start_ms, end_ms)
    series.extend(request_series)

    sources = ["nvml"]
    if eng_samples:
        sources.append("lmcompat")
    if request_series:
        sources.append(JSONL_SOURCE)

    run_id = f"run-{started.replace(':', '').replace('-', '')}"
    run = Run(
        id=run_id,
        started_at=started,
        ended_at=ended,
        hardware=hardware,
        workload=workload,
        sampling=dict(sampling),
        sources=sources,
        artifacts=[jsonl_path] if jsonl_path else [],
        series=series,
    )
    dest = Path(out)
    if dest.suffix == ".json":
        dest.parent.mkdir(parents=True, exist_ok=True)
        run.id = dest.stem
        return save_run(run, dest.parent)
    return save_run(run, dest)
