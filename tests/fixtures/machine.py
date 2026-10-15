"""Machine facts the tests need, in one place.

Nothing here probes at import time. A test that needs a file on disk asks for
the skip reason instead of hardcoding a path in its own body.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request

# The engine's endpoint as recorded in docs/MILESTONE-1.md. llama-swap injects
# the port per model at launch, so a live session must resolve the port with
# resolve_engine_port() rather than trust ENGINE_PORT: the backend was on 5804
# when the milestone was written and on 5806 on 2026-10-15.
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 5804

# What the live engine loads today (llama-swap NINFER_MODEL_V3), and what the
# recorded counters in docs/MILESTONE-1.md were measured against (v2). The two
# files differ by 218608 bytes, so a fixture keeps the v2 byte count on purpose.
LIVE_ARTIFACT_PATH = "/home/tcrypt/ninfer-v3-artifacts/qwen3_8_27b.v3.ninfer"
RECORDED_ARTIFACT_PATH = "/home/tcrypt/ninfer-4090/models/qwen3_8_27b.ninfer"
RECORDED_ARTIFACT_BYTES = 18210531328

# The request log the live backend appends, enabled with --request-log-jsonl
# in the llama-swap entry. observe() skips it quietly when absent, so a run
# without it is NVML-only rather than an error.
REQUEST_LOG_PATH = "/home/tcrypt/ninfer-4090/logs/ninfer-qwen3_8_27b.jsonl"


def artifact_bytes(path: str) -> int | None:
    """The file's real size, or None when this machine does not have it."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def missing_artifact_reason(path: str) -> str:
    return f"artifact {path} is absent on this machine"


_resolved_port: int | None = None


def resolve_engine_port() -> int:
    """The live backend's port, whatever llama-swap assigned it.

    Order: SPECTRA_ENGINE_PORT when set, else the listening port whose
    /v1/models lists an NInfer model, else ENGINE_PORT. Memoised, and never
    probed at import time -- call it where the live session starts.
    """
    global _resolved_port
    if _resolved_port is not None:
        return _resolved_port
    override = os.environ.get("SPECTRA_ENGINE_PORT", "")
    if override.isdigit() and 1 <= int(override) <= 65535:
        _resolved_port = int(override)
        return _resolved_port
    for port in _listening_ports():
        if _serves_ninfer(ENGINE_HOST, port):
            _resolved_port = port
            return _resolved_port
    _resolved_port = ENGINE_PORT
    return _resolved_port


def _listening_ports() -> list[int]:
    try:
        out = subprocess.run(["ss", "-tln"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    ports: list[int] = []
    for line in out.splitlines():
        fields = line.split()
        local = fields[3] if len(fields) > 3 else ""
        host, _, port = local.rpartition(":")
        if host == ENGINE_HOST and port.isdigit():
            ports.append(int(port))
    return ports


def _serves_ninfer(host: str, port: int) -> bool:
    # The swap proxy on 9090 also lists NInfer models, so /v1/models alone
    # cannot tell the proxy from the backend: the backend's /health answers
    # JSON {"status": "ok"} while the proxy answers plain "OK".
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2) as response:
            health = json.loads(response.read().decode())
    except Exception:
        return False
    if not isinstance(health, dict) or health.get("status") != "ok":
        return False
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=2) as response:
            payload = json.loads(response.read().decode())
    except Exception:
        return False
    models = payload.get("data", []) if isinstance(payload, dict) else []
    return any("NInfer" in str(m.get("id", "")) for m in models if isinstance(m, dict))
