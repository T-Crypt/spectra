"""Shared test guards and helpers.

Nothing here runs at import time. Every probe is memoised, so a module that
only wants the guard pays for one probe per process, and a test file imported
without a GPU or a server performs no side effect.
"""

from __future__ import annotations

import urllib.request

NO_GPU_REASON = "no GPU or NVML unavailable"

_gpu: bool | None = None
_engines: dict[tuple[str, int], bool] = {}


def gpu_available() -> bool:
    """True when NVML loads and one sample can be taken.

    Only the two errors that mean "no NVML on this machine" count as absent: the
    library not loading (``OSError``) and an NVML call refusing (``RuntimeError``
    from the adapter's own result check). Anything else is a broken adapter, and
    it propagates: a hardware test that skips on a bug in the adapter loses its
    own coverage without saying so.
    """
    global _gpu
    if _gpu is None:
        try:
            from adascope.adapters.nvml import Nvml

            Nvml.sample()
            _gpu = True
        except (OSError, RuntimeError):
            _gpu = False
    return _gpu


def engine_available(host: str, port: int, timeout_s: float = 1.0) -> bool:
    """True when the engine answers /health (or /metrics) on host:port."""
    key = (host, port)
    if key not in _engines:
        _engines[key] = _probe(host, port, timeout_s)
    return _engines[key]


def engine_down_reason(host: str, port: int) -> str:
    return f"engine at {host}:{port} is down"


def _probe(host: str, port: int, timeout_s: float) -> bool:
    for path in ("/health", "/metrics"):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout_s) as response:
                if response.status == 200:
                    return True
        except Exception:
            continue
    return False
