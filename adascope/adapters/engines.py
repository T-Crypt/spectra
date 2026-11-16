"""Engine metric name mapping.

The analyser reads a fixed set of canonical series names. The engines write
different names for the same quantities, so this module owns the table that
maps one engine's native names onto the canonical ones, and the probe that
recognises which engine is answering on a port.

Names and counter sets were read from the engines' own source on 2026-11-16,
never guessed:

* ninfer (the local engine lineage): ``src/serve/serve_metrics.cpp``.
  Emits ``llamacpp:tokens_predicted_total``,
  ``llamacpp:tokens_predicted_seconds_total``, ``llamacpp:draft_tokens_total``,
  ``llamacpp:draft_accepted_tokens_total``.
* llama.cpp (``llama-server --metrics``): ``tools/server/server-task.cpp``,
  checked at build b12024. Emits the same core counter names as ninfer plus
  ``llamacpp:n_decode_total`` and, for speculative decoding,
  ``llamacpp:spec_decode_num_draft_tokens_total``,
  ``llamacpp:spec_decode_num_accepted_tokens_total`` and
  ``llamacpp:spec_decode_num_drafts_total`` (verification steps, i.e. rounds).
* vLLM (v1 engine): ``vllm/v1/metrics/loggers.py`` on the main branch.
  Emits ``vllm:generation_tokens_total`` and carries no decode-seconds
  counter, so a vLLM run takes its decode rate from the wall-window fallback
  in the analyser rather than from a counter pair. It also carries no draft
  counters, so the spec factor stays at the no-speculation default.

A name that the table does not know passes through unchanged, prefix
stripped: the run stores what the engine emitted, and a later rule may read
it.
"""

from __future__ import annotations

#: The engines the table knows, in the order detection prefers to name them.
ENGINE_IDS = ("ninfer", "llamacpp", "vllm")

#: Every metric name prefix the engines emit.
KNOWN_PREFIXES = ("llamacpp:", "ninfer:", "vllm:")

# Canonical series name -> native name, per engine. A canonical name absent
# from an engine's map is one that engine does not emit.
_CANNONICAL = {
    "ninfer": {
        "tokens_predicted_total": "tokens_predicted_total",
        "tokens_predicted_seconds_total": "tokens_predicted_seconds_total",
        "draft_tokens_total": "draft_tokens_total",
        "draft_accepted_tokens_total": "draft_accepted_tokens_total",
    },
    "llamacpp": {
        "tokens_predicted_total": "tokens_predicted_total",
        "tokens_predicted_seconds_total": "tokens_predicted_seconds_total",
        "draft_tokens_total": "spec_decode_num_draft_tokens_total",
        "draft_accepted_tokens_total": "spec_decode_num_accepted_tokens_total",
        "draft_rounds_total": "spec_decode_num_drafts_total",
    },
    "vllm": {
        "tokens_predicted_total": "generation_tokens_total",
    },
}

_NATIVE_TO_CANNONICAL = {
    engine: {native: canonical for canonical, native in table.items()}
    for engine, table in _CANNONICAL.items()
}


def strip_prefix(name: str) -> str:
    """Remove exactly one known engine prefix. A name with none is unchanged."""
    for prefix in KNOWN_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def detect_engine(raw_names) -> tuple[str, str]:
    """Which engine emits this /metrics body, and the marker that decided it.

    ``raw_names`` is the set of metric names with their prefixes, as parsed
    from one /metrics body. The probe needs one fetch and no privileges:

    * any ``vllm:`` name identifies vLLM; its prefix is unique to it.
    * ``n_decode_total`` identifies llama.cpp; current builds always emit it
      and ninfer does not.
    * a bare ``draft_tokens_total`` identifies ninfer; llama.cpp names its
      draft counters ``spec_decode_*``.
    * nothing recognised falls back to llama.cpp naming, which shares the
      core counter names with ninfer, so a run still gets a decode rate.
    """
    names = {strip_prefix(n) for n in raw_names}
    if any(n.startswith("vllm:") for n in raw_names):
        return "vllm", "vllm: prefix"
    if "n_decode_total" in names:
        return "llamacpp", "n_decode_total counter"
    if "draft_tokens_total" in names:
        return "ninfer", "draft_tokens_total counter"
    return "llamacpp", "default: tokens_predicted_* naming"


def canonical_name(engine: str, name: str) -> str:
    """One stored series name for a metric the given engine emitted.

    The prefix comes off first, then the engine's table maps the native name
    onto the canonical one. A name the table does not keep passes through
    stripped: the run records what the engine emitted.
    """
    if engine not in _CANNONICAL:
        raise ValueError(f"unknown engine {engine!r}; expected one of {', '.join(ENGINE_IDS)}")
    bare = strip_prefix(name)
    return _NATIVE_TO_CANNONICAL[engine].get(bare, bare)
