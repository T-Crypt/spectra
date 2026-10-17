"""Memory-bound dense decode reference model.

Pure function of its inputs. The store holds raw measurements. Analysis calls
this at report time, never stores its output in Phase 1.

This module asserts no speculative factor of its own. ``spec_tokens_per_forward``
is an explicit argument: the analyser derives it from the run's own counters,
and the caller that wants the pre-speculation ceiling passes 1.0.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import Quality, ReferenceModel


def default_profile_path() -> Path:
    """The architecture profile shipped with the package."""
    return Path(__file__).resolve().parent / "profiles" / "sm89.json"


def load_profile(path: str | Path | None = None) -> dict:
    """Read an architecture profile. Resolution never depends on the CWD."""
    with open(path or default_profile_path(), encoding="utf-8") as handle:
        return json.load(handle)


def dense_decode_reference(
    artifact_bytes: int,
    kv_bytes_per_token: float = 0.0,
    context_tokens: int = 0,
    bandwidth_gbps: float = 1008.0,
    spec_tokens_per_forward: float = 1.0,
) -> ReferenceModel:
    """Ceiling for dense decode when memory bandwidth is the only limit."""
    bytes_per_forward = artifact_bytes + kv_bytes_per_token * context_tokens
    ceiling = bandwidth_gbps * 1e9 / bytes_per_forward * spec_tokens_per_forward
    return ReferenceModel(
        workload_class="dense-decode",
        objective_unit="tok/s",
        ceiling=ceiling,
        limiting_resource="memory_bandwidth",
        derivation={
            "formula": "bandwidth_gbps * 1e9 / bytes_per_forward * tokens_per_forward",
            "inputs": {
                "artifact_bytes": artifact_bytes,
                "kv_bytes_per_token": kv_bytes_per_token,
                "context_tokens": context_tokens,
                "bandwidth_gbps": bandwidth_gbps,
                "spec_tokens_per_forward": spec_tokens_per_forward,
            },
            "assumptions": [
                "weights are read once per forward pass during decode",
                "KV-cache bytes add linearly per context token",
                "speculative decoding multiplies tokens per forward pass",
                "draft-head weights are counted inside artifact_bytes",
            ],
        },
        quality=Quality.DERIVED,
    )
