"""First-party workload driver.

``observe`` only watches, and a run without traffic has no rate. ``bench``
drives the engine's OpenAI-compatible chat endpoint itself, so a run always
carries the workload that produced it, recorded in the run's config and as
measured series.

The driver is one streamed greedy completion per call, ``concurrency`` calls
in flight, and it records what actually happened, completions and failures,
rather than assuming the load materialised. A failed attempt sleeps one
second and retries, so a dead engine takes the run to zero completions
instead of ending the thread; the failure series says so.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from collections.abc import Callable

from .model import Quality, Series

BASE_SENTENCE = "The quick brown fox jumps over the lazy dog."


def build_prompt(words: int) -> tuple[str, int]:
    """A deterministic prompt of exactly ``words`` words, and its word count.

    The same input always gives the same text, so a run's fingerprint is
    reproducible without storing the prompt itself. The count is what the
    text actually carries, measured by splitting it, not the input echoed
    back.
    """
    if not isinstance(words, int) or isinstance(words, bool) or words < 1:
        raise ValueError(f"prompt words must be a positive int, got {words!r}")
    unit = BASE_SENTENCE.split()
    parts = (unit * (words // len(unit) + 1))[:words]
    text = " ".join(parts)
    return text, len(text.split())


def validate_load(load: dict) -> dict:
    """The driver config, validated before any I/O happens."""
    if not isinstance(load, dict):
        raise ValueError(f"load config must be a dict, got {type(load).__name__}")
    out = {}
    for key in ("prompt_words", "completion_tokens", "concurrency"):
        value = load.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{key} must be a positive int, got {value!r}")
        out[key] = value
    return out


def driver_series(events: list[tuple[float, str]]) -> list[Series]:
    """Cumulative completion and failure series from driver events.

    ``events`` are (offset_seconds, kind) with kind "completed" or "failed",
    in the order the driver saw them. The completed series is always present
    so a run under load always says how many requests finished, zero
    included. The failed series is present only when something failed.
    """
    completed = failed = 0
    completed_points: list[tuple[float, float]] = []
    failed_points: list[tuple[float, float]] = []
    for offset, kind in sorted(events):
        if kind == "completed":
            completed += 1
            completed_points.append((offset, completed))
        else:
            failed += 1
            failed_points.append((offset, failed))
    series = [
        Series(metric="driver_requests_completed", unit="count", source="bench",
               quality=Quality.MEASURED, samples=completed_points),
    ]
    if failed_points:
        series.append(
            Series(metric="driver_requests_failed", unit="count", source="bench",
                   quality=Quality.MEASURED, samples=failed_points))
    return series


def stream_completion(host: str, port: int, model: str, max_tokens: int = 256,
                      prompt: str = BASE_SENTENCE, timeout_s: float = 600.0) -> dict:
    """One streamed greedy completion. Returns the last chunk the engine sent.

    Only fields the engine documents are sent: model id, one user message, a
    greedy temperature, a token ceiling and streaming.
    """
    url = f"http://{host}:{port}/v1/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": True,
    }).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    last: dict = {}
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            try:
                payload = json.loads(chunk)
            except ValueError:
                continue
            if isinstance(payload, dict):
                last = payload
    return last


def start_driver(host: str, port: int, model: str, prompt: str, max_tokens: int,
                 concurrency: int, record: Callable[[float, str], None],
                 wall_start: float) -> tuple[threading.Event, list[threading.Thread]]:
    """Start ``concurrency`` completion slots in the background.

    ``record(offset_seconds, kind)`` is called for every finished attempt,
    "completed" or "failed", offset from ``wall_start``. The caller owns the
    lock around ``record``'s target if it shares it. The returned ``stop``
    event ends the slots; the caller sets it and joins the threads.
    """
    stop = threading.Event()

    def slot() -> None:
        while not stop.is_set():
            offset = time.monotonic() - wall_start
            try:
                stream_completion(host, port, model, max_tokens=max_tokens,
                                  prompt=prompt, timeout_s=120.0)
                record(offset, "completed")
            except Exception:
                # A dead engine must not end the thread: sleep and retry so
                # the window fills with failures the run can show.
                record(offset, "failed")
                time.sleep(1.0)

    threads = [threading.Thread(target=slot, daemon=True) for _ in range(concurrency)]
    for thread in threads:
        thread.start()
    return stop, threads


def drive_decode(host: str, port: int, model: str, stop, max_tokens: int = 256) -> dict:
    """Keep one completion in flight until ``stop`` is set. Returns the last reply.

    A failed request sleeps one second and retries: the first failure used to
    end the thread, which left a full repetition with power draw and no
    completed requests, and nothing said why. ``drive_errors`` counts the
    failures so a repetition with errors says so.
    """
    last: dict = {}
    errors = 0
    while not stop.is_set():
        try:
            last = stream_completion(host, port, model, max_tokens=max_tokens, timeout_s=120.0)
        except Exception as exc:  # a dead engine must not take the eval down
            errors += 1
            last = {"error": str(exc), "drive_errors": errors}
            time.sleep(1.0)
    if errors:
        last = dict(last, drive_errors=errors)
    return last
