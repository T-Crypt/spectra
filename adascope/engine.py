"""Structured rule evaluator and sm_89 rules.

Rules are data in adascope/rules/*.json. The predicate language has no eval:
conjunction, disjunction, negation, comparisons against a flat fact dict, and
boolean flags. A new architecture is a new JSON file.

The rule set is validated on load, at the boundary: a rule file that names an
unknown claim kind, an unknown quality, or a missing key is a bug, not a
silently quieter diagnosis. The analyser never keys off a rule id; it reads the
evidence each rule declares.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ClaimKind, Quality

REQUIRED_RULE_KEYS = (
    "id",
    "applies_when",
    "claim",
    "claim_kind",
    "confidence_basis",
    "evidence_observations",
)


def _resolve(field: str, facts: dict[str, Any]) -> Any:
    return facts.get(field)


def evaluate(predicate: Any, facts: dict[str, Any]) -> bool:
    if isinstance(predicate, dict):
        if "all" in predicate:
            return all(evaluate(p, facts) for p in predicate["all"])
        if "any" in predicate:
            return any(evaluate(p, facts) for p in predicate["any"])
        if "not" in predicate:
            return not evaluate(predicate["not"], facts)
        if "bool" in predicate:
            return bool(_resolve(predicate["bool"], facts))
        for op in ("gt", "lt", "ge", "le", "eq"):
            if op in predicate:
                field, want = predicate[op]
                got = _resolve(field, facts)
                if got is None or isinstance(got, bool):
                    return False
                try:
                    if op == "gt":
                        return got > want
                    if op == "lt":
                        return got < want
                    if op == "ge":
                        return got >= want
                    if op == "le":
                        return got <= want
                    return got == want
                except TypeError:
                    return False
    raise ValueError(f"malformed predicate: {predicate!r}")


def fires(rule: dict[str, Any], facts: dict[str, Any]) -> bool:
    return evaluate(rule["applies_when"], facts)


def rule_confidence(rule: dict[str, Any], facts: dict[str, Any]) -> Quality:
    """The quality the rule's evidence actually supports.

    The first entry of confidence_basis whose ``when`` is absent or true wins.
    A rule whose bit is absent from the run must not print measured.
    """
    for entry in rule.get("confidence_basis", []):
        when = entry.get("when")
        if when is None or evaluate(when, facts):
            return Quality(entry["quality"])
    return Quality.HYPOTHESIS


def _validate_rule(rule: Any) -> None:
    if not isinstance(rule, dict):
        raise ValueError(f"rule must be a JSON object, got {rule!r}")
    rule_id = rule.get("id", "<no id>")
    for key in REQUIRED_RULE_KEYS:
        if key not in rule:
            raise ValueError(f"rule {rule_id} is missing key {key!r}")
    try:
        ClaimKind(rule["claim_kind"])
    except ValueError:
        raise ValueError(f"rule {rule_id} has unknown claim_kind {rule['claim_kind']!r}") from None
    basis = rule["confidence_basis"]
    if not isinstance(basis, list) or not basis:
        raise ValueError(f"rule {rule_id} needs a non-empty confidence_basis list")
    for entry in basis:
        if not isinstance(entry, dict) or "quality" not in entry:
            raise ValueError(f"rule {rule_id} has a malformed confidence_basis entry {entry!r}")
        try:
            Quality(entry["quality"])
        except ValueError:
            raise ValueError(f"rule {rule_id} has unknown confidence quality {entry['quality']!r}") from None
    if not isinstance(rule["evidence_observations"], list):
        raise ValueError(f"rule {rule_id} needs evidence_observations to be a list")


def load_rules(path: str | Path) -> list[dict[str, Any]]:
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rules, list):
        raise ValueError(f"rule set {path} must hold a JSON list")
    for rule in rules:
        _validate_rule(rule)
    return rules


def default_rules_path() -> Path:
    return Path(__file__).parent / "rules" / "sm89.json"
