"""Machine facts the tests need, in one place.

Nothing here probes at import time. A test that needs a file on disk asks for
the skip reason instead of hardcoding a path in its own body.
"""

from __future__ import annotations

import os

# The engine's endpoint as recorded in docs/MILESTONE-1.md. llama-swap injects
# the port per model at launch, so a live session must read the port from
# llama-swap rather than trust this value.
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 5804

# What the live engine loads today (llama-swap NINFER_MODEL_V3), and what the
# recorded counters in docs/MILESTONE-1.md were measured against (v2). The two
# files differ by 218608 bytes, so a fixture keeps the v2 byte count on purpose.
LIVE_ARTIFACT_PATH = "/home/tcrypt/ninfer-v3-artifacts/qwen3_8_27b.v3.ninfer"
RECORDED_ARTIFACT_PATH = "/home/tcrypt/ninfer-4090/models/qwen3_8_27b.ninfer"
RECORDED_ARTIFACT_BYTES = 18210531328


def artifact_bytes(path: str) -> int | None:
    """The file's real size, or None when this machine does not have it."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def missing_artifact_reason(path: str) -> str:
    return f"artifact {path} is absent on this machine"
