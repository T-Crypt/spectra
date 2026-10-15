"""A small stdlib load driver, for the eval and the live fidelity check.

One streamed greedy completion per call, over the documented OpenAI path. This
is a test helper, not a Phase 1 feature.

The driver cannot switch thinking off: the live launch sets
``--default-thinking-budget 4096``, so a "short" completion may still run for a
while. Callers must therefore check that the counters moved inside the window
rather than assume the load materialised, and record inconclusive when they
did not.
"""

from __future__ import annotations

import json
import urllib.request

PROMPT = "Write one paragraph about memory bandwidth in GPU inference."
MAX_TOKENS = 256


def stream_completion(host: str, port: int, model: str, max_tokens: int = MAX_TOKENS,
                      prompt: str = PROMPT, timeout_s: float = 600.0) -> dict:
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


def drive_decode(host: str, port: int, model: str, stop, max_tokens: int = MAX_TOKENS) -> dict:
    """Keep one completion in flight until ``stop`` is set. Returns the last reply."""
    last: dict = {}
    while not stop.is_set():
        try:
            last = stream_completion(host, port, model, max_tokens=max_tokens, timeout_s=120.0)
        except Exception as exc:  # a dead engine must not take the eval down
            last = {"error": str(exc)}
            return last
    return last
