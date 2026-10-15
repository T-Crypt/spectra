"""lmcompat engine adapter.

This module is one of the two places that touch foreign formats. It speaks
plain HTTP with urllib, parses the Prometheus text body and /v1/models here,
and reads the engine's schema v20 request log. Everything downstream trusts
the types.

Field names in the request log are the ones the engine actually writes; they
were read out of the engine source, never guessed. See ``_request_from_record``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, NamedTuple

from ..model import Workload

KNOWN_PREFIXES = ("llamacpp:", "ninfer:")

SCHEMA_VERSION = 20


def parse_metrics_text(body: str) -> dict[str, float]:
    """Parse a Prometheus text body into a name to float map.

    Keys keep their full names, for example ``llamacpp:tokens_predicted_total``.
    No stripped alias is added: two keys for one number invites a caller to sum
    both. Use :func:`strip_known_prefix` when a bare series name is wanted.
    A repeated name keeps its last value.
    """
    out: dict[str, float] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition("{")
        if not rest:
            name, _, value = line.partition(" ")
        else:
            _, _, value = rest.partition("}")
        name = name.strip()
        try:
            number = float(value.strip().split(" ")[0])
        except ValueError:
            continue
        out[name] = number
    return out


def strip_known_prefix(name: str) -> str:
    """Remove exactly one of the engine's metric name prefixes."""
    for prefix in KNOWN_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


class JsonlRequest(NamedTuple):
    """One request_done record, in the fields Spectra uses.

    The first six fields are the payload; the last two come from the record's
    own event envelope and are what let an observer keep only the requests of
    the engine instance it was watching.
    """

    completion_tokens: int
    decode_seconds: float
    rounds: int | None
    drafted_tokens: int | None
    accepted_tokens: int | None
    draft_window: int | None
    timestamp_unix_ms: int | None = None
    server_instance_id: str | None = None


@dataclass
class JsonlSummary:
    """What a --request-log-jsonl file holds, in Spectra's terms.

    ``config`` carries the whole ``server_start`` record under its own key,
    so the launch configuration is stored, not summarised.
    """

    config: dict[str, Any] = field(default_factory=dict)
    requests: list[JsonlRequest] = field(default_factory=list)
    schema_version: int | None = None

    @property
    def server_start(self) -> dict[str, Any]:
        record = self.config.get("server_start")
        return record if isinstance(record, dict) else {}

    @property
    def server_instance_id(self) -> str | None:
        """The id of the engine instance whose server_start record is last."""
        value = self.server_start.get("server_instance_id")
        return value if isinstance(value, str) else None

    @property
    def request_count(self) -> int:
        return len(self.requests)

    def artifact_size_bytes(self) -> int | None:
        artifact = self.server_start.get("artifact")
        if not isinstance(artifact, dict):
            return None
        size = _number(artifact.get("size_bytes"))
        return int(size) if size is not None else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _request_from_record(record: dict[str, Any]) -> JsonlRequest | None:
    """Extract one request_done record, or None when it lacks the fields.

    Schema v20 keys, read from the engine source: ``result.completion_tokens``,
    ``timings_seconds.decode``, and the ``speculative`` block. A record with no
    decode time or no completion token count is skipped: Spectra reports
    nothing rather than inventing a field.
    """
    timings = record.get("timings_seconds")
    if not isinstance(timings, dict):
        return None
    decode_seconds = _number(timings.get("decode"))
    if decode_seconds is None or decode_seconds <= 0:
        return None
    result = record.get("result")
    result = result if isinstance(result, dict) else {}
    completion = _number(result.get("completion_tokens"))
    if completion is None:
        return None
    speculative = record.get("speculative")
    speculative = speculative if isinstance(speculative, dict) else {}
    return JsonlRequest(
        completion_tokens=int(completion),
        decode_seconds=decode_seconds,
        rounds=_int_or_none(speculative.get("rounds")),
        drafted_tokens=_int_or_none(speculative.get("drafted_tokens")),
        accepted_tokens=_int_or_none(speculative.get("accepted_tokens")),
        draft_window=_int_or_none(speculative.get("draft_window")),
        timestamp_unix_ms=_int_or_none(record.get("timestamp_unix_ms")),
        server_instance_id=record.get("server_instance_id")
        if isinstance(record.get("server_instance_id"), str)
        else None,
    )


def parse_jsonl_lines(lines: Iterable[str]) -> JsonlSummary:
    """Read request-log lines into a summary.

    The reader is gated on :data:`SCHEMA_VERSION`. A record carrying a different
    version ends the read and the caller gets an empty summary: a version this
    reader does not know may mean different keys, and one wrong field is worse
    than a number Spectra reports as unavailable. A line that is not JSON, or a
    record whose ``event`` is not one of the two this reader understands, is
    skipped without raising for the same reason.
    """
    summary = JsonlSummary()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        version = _int_or_none(record.get("schema_version"))
        if version is not None:
            if version != SCHEMA_VERSION:
                return JsonlSummary()
            summary.schema_version = version
        event = record.get("event")
        if event == "server_start":
            # Last wins: the file is appended to across restarts, and the
            # instance being observed is the one that started last.
            summary.config["server_start"] = record
        elif event == "request_done":
            request = _request_from_record(record)
            if request is not None:
                summary.requests.append(request)
    return summary


def parse_jsonl(path: str | os.PathLike[str]) -> JsonlSummary:
    """Read a --request-log-jsonl file for its launch config and its requests."""
    with open(path, encoding="utf-8") as handle:
        return parse_jsonl_lines(handle)


class LmCompat:
    """HTTP client for an lmcompat-style inference server."""

    def __init__(self, host: str, port: int, timeout_s: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s

    def _get(self, path: str) -> tuple[int, str]:
        url = f"http://{self.host}:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout_s) as response:
            return response.status, response.read().decode()

    def metrics(self) -> dict[str, float]:
        status, body = self._get("/metrics")
        if status != 200:
            raise RuntimeError(f"GET /metrics returned {status}")
        return parse_metrics_text(body)

    def models(self) -> list[dict]:
        status, body = self._get("/v1/models")
        if status != 200:
            raise RuntimeError(f"GET /v1/models returned {status}")
        payload = json.loads(body)
        if isinstance(payload, dict):
            data = payload.get("data", [])
            return list(data) if isinstance(data, list) else []
        return list(payload) if isinstance(payload, list) else []

    def workload(
        self,
        model_id: str,
        config: dict[str, Any] | None = None,
        artifact_path: str = "",
        jsonl_path: str | None = None,
    ) -> Workload:
        """Build the workload for one observed session.

        The operator's ``config`` is merged over the request log's own
        ``server_start`` record, and the artifact size is the local file's size
        when the path exists here, else the size the engine recorded, else
        None.
        """
        summary = parse_jsonl(jsonl_path) if jsonl_path and os.path.isfile(jsonl_path) else None
        merged: dict[str, Any] = dict(summary.config) if summary is not None else {}
        merged.update({str(k): v for k, v in (config or {}).items()})

        artifact_bytes: int | None = None
        if artifact_path and os.path.isfile(artifact_path):
            artifact_bytes = os.path.getsize(artifact_path)
        elif summary is not None:
            artifact_bytes = summary.artifact_size_bytes()

        return Workload(
            adapter_id="lmcompat",
            engine_id="ninfer",
            engine_version=None,
            model_id=model_id,
            artifact_path=artifact_path,
            artifact_bytes=artifact_bytes,
            artifact_sha256=None,
            objective={"metric": "decode_tokens_per_second", "direction": "maximize", "target": None},
            constraints={"latency_slo_ms": None, "memory_budget_bytes": None},
            config=merged,
        )
