from __future__ import annotations

import json
from dataclasses import MISSING, dataclass, field, asdict, fields as dataclass_fields
from enum import Enum
from typing import Any, get_type_hints


class ModelError(ValueError):
    """A stored mapping does not match the domain type it claims to be."""


class Quality(str, Enum):
    MEASURED = "measured"
    DERIVED = "derived"
    HYPOTHESIS = "hypothesis"


class ClaimKind(str, Enum):
    BOUNDED_BY = "bounded_by"
    STARVED = "starved"
    CONTENDED = "contended"
    MISCONFIGURED = "misconfigured"


class Direction(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    APPROVED = "approved"
    RUNNING = "running"
    DONE = "done"
    ABORTED = "aborted"


class FindingVerdict(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class ComparisonVerdict(str, Enum):
    COMPARABLE = "comparable"
    COMPARABLE_WITH_NORMALIZATION = "comparable_with_normalization"
    NOT_COMPARABLE = "not_comparable"


@dataclass
class HardwareProfile:
    name: str
    arch: str
    compute_capability: str
    vram_total_bytes: int
    mem_bandwidth_spec_gbps: float | None = None
    mem_bandwidth_measured_gbps: float | None = None
    pcie_link_gen: int | None = None
    pcie_link_width: int | None = None
    sm_count: int | None = None
    l2_bytes: int | None = None
    power_limit_w: float | None = None
    power_default_w: float | None = None
    power_max_w: float | None = None
    clock_sm_max_mhz: int | None = None
    clock_mem_max_mhz: int | None = None
    driver_version: str | None = None
    cuda_driver_version: str | None = None


@dataclass
class Workload:
    adapter_id: str
    engine_id: str
    engine_version: str | None = None
    model_id: str | None = None
    artifact_path: str | None = None
    artifact_bytes: int | None = None
    artifact_sha256: str | None = None
    objective: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


@dataclass
class Series:
    metric: str
    unit: str
    source: str
    quality: Quality
    samples: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Run:
    id: str
    started_at: str
    ended_at: str
    hardware: HardwareProfile
    workload: Workload
    sampling: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    # Environment the observation happened in, recorded not recomputed.
    # Today: a first-tick snapshot of the card's compute processes under
    # "gpu_processes". Runs stored before the field existed carry no key and
    # load with the empty default.
    environment: dict = field(default_factory=dict)


@dataclass
class Observation:
    run_id: str
    metric: str
    value: float
    unit: str
    window: tuple[float, float] | str
    comparison: str
    method: str
    source_series: list[str] = field(default_factory=list)


@dataclass
class ReferenceModel:
    workload_class: str
    objective_unit: str
    ceiling: float
    limiting_resource: str
    derivation: dict = field(default_factory=dict)
    quality: Quality = Quality.DERIVED


@dataclass
class Hypothesis:
    id: str
    run_id: str
    claim: str
    mechanism: str = ""
    rank_score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    alternatives: list["Hypothesis"] = field(default_factory=list)
    confidence: Quality = Quality.HYPOTHESIS


@dataclass
class Experiment:
    id: str
    hypothesis_id: str
    baseline_run_id: str
    variable: str
    baseline_value: Any = None
    treatment_value: Any = None
    success_criteria: dict = field(default_factory=dict)
    rollback: dict = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.PLANNED
    treatment_run_id: str | None = None
    notes: str = ""


@dataclass
class Finding:
    id: str
    hypothesis_id: str
    experiment_id: str | None = None
    verdict: FindingVerdict = FindingVerdict.INCONCLUSIVE
    delta: dict = field(default_factory=dict)
    notes: str = ""
    artifacts: list[str] = field(default_factory=list)
    arch: str | None = None
    engine_id: str | None = None
    workload_class: str | None = None
    variable: str | None = None
    direction: str | None = None


@dataclass
class Fingerprint:
    run_id: str
    arch: str
    engine_id: str
    engine_version: str | None = None
    model_id: str | None = None
    artifact_bytes: int | None = None
    artifact_sha256: str | None = None
    objective: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    hardware_name: str | None = None
    driver_version: str | None = None
    cuda_driver_version: str | None = None
    contention: bool = False
    sources: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    sampling: dict = field(default_factory=dict)
    created_at: str | None = None


@dataclass
class Comparison:
    run_a_id: str
    run_b_id: str
    verdict: ComparisonVerdict = ComparisonVerdict.NOT_COMPARABLE
    reason: str = ""
    differences: list[dict] = field(default_factory=list)
    config_diff: list[dict] = field(default_factory=list)
    metric_deltas: dict = field(default_factory=dict)


def _enum_value(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    return v


def to_dict(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [to_dict(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    return obj


def _required_fields(cls) -> list[str]:
    """Field names a mapping must carry: no default and no default factory."""
    return [
        f.name
        for f in dataclass_fields(cls)
        if f.default is MISSING and f.default_factory is MISSING
    ]


def _check_keys(cls, d: dict) -> None:
    """Reject non-mapping input, unknown and missing keys, naming the field."""
    if not isinstance(d, dict):
        raise ModelError(f"{cls.__name__} expects a JSON object, got {type(d).__name__}")
    known = set(get_type_hints(cls))
    unknown = sorted(set(d) - known)
    if unknown:
        raise ModelError(f"{cls.__name__} has no field {unknown[0]!r}")
    missing = sorted(set(_required_fields(cls)) - set(d))
    if missing:
        raise ModelError(f"{cls.__name__} is missing required field {missing[0]!r}")


def _pair(cls, key: str, item) -> tuple:
    """One [timestamp, value] pair, or a domain error naming the field."""
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return (item[0], item[1])
    raise ModelError(f"{cls.__name__}.{key} expects [timestamp, value] pairs, got {item!r}")


def _construct(cls, d: dict):
    """Build a dataclass from a dict, coercing enums and tuples.

    This is a *shape* check, not a value check. It rejects a non-mapping, an
    unknown key, a missing key with no default, a nested payload that is not an
    object, a list or a pair of the wrong shape, and an enum value no member
    matches. The first five raise a :class:`ModelError` naming the class and,
    for a nested payload, the field it sits in; the enum case raises the enum's
    own ``ValueError`` naming the value. Either way the CLI prints one line and
    exits 2, instead of letting a generated ``TypeError`` escape from a
    consumer.

    What it deliberately does *not* check is a scalar's Python type: a
    ``power_limit_w`` holding the string ``"450"``, a null ``metric``, or a
    sample that is not a number is handed to the dataclass as it stands. A field
    the analysis reads then fails in that consumer -- ``TypeError`` for the
    first and third, ``AttributeError`` for the second, one traceback and exit
    1, not 2 -- and a field nothing reads carries the wrong type in silence.
    No producer in this tree can write one (``observe`` stores numbers only),
    and a type guess here (is an ``int`` acceptable where a ``float`` is
    declared? is a numeric string?) would reject more legitimate files than it
    saves, so the limit is stated rather than half-enforced.
    """
    _check_keys(cls, d)
    hints = get_type_hints(cls)
    kwargs = {}
    for key, value in d.items():
        hint = hints.get(key)
        if hint is None:
            kwargs[key] = value
            continue
        origin = getattr(hint, "__origin__", None)
        # Enum fields
        if isinstance(hint, type) and issubclass(hint, Enum):
            kwargs[key] = hint(value)
        # tuple field (samples, window)
        elif origin is tuple:
            if value == "steady" or isinstance(value, str):
                kwargs[key] = value
            elif isinstance(value, (list, tuple)):
                kwargs[key] = tuple(value)
            else:
                raise ModelError(f"{cls.__name__}.{key} expects a tuple, got {type(value).__name__}")
        # list of dataclasses (series, alternatives) or of pairs (samples)
        elif origin is list:
            if not isinstance(value, list):
                raise ModelError(f"{cls.__name__}.{key} expects a list, got {type(value).__name__}")
            args = getattr(hint, "__args__", ())
            if args and isinstance(args[0], type) and hasattr(args[0], "__dataclass_fields__"):
                kwargs[key] = [_construct(args[0], item) for item in value]
            elif args and getattr(args[0], "__origin__", None) is tuple:
                kwargs[key] = [_pair(cls, key, item) for item in value]
            else:
                kwargs[key] = value
        # nested dataclass (hardware, workload)
        elif isinstance(hint, type) and hasattr(hint, "__dataclass_fields__"):
            try:
                kwargs[key] = _construct(hint, value)
            except ModelError as exc:
                raise ModelError(f"{cls.__name__}.{key}: {exc}") from None
        else:
            kwargs[key] = value
    return cls(**kwargs)


def from_dict(cls, d: dict):
    return _construct(cls, d)


def run_to_json(run: Run) -> str:
    return json.dumps(to_dict(run), indent=2, sort_keys=False)


def run_from_json(text: str) -> Run:
    return _construct(Run, json.loads(text))
