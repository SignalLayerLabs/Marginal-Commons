"""Strict stdlib validation for Commons aggregate source documents."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import cast


class ValidationError(ValueError):
    """Raised when a Commons source document is outside the closed contract."""


ATOM_FIELDS = frozenset(
    {
        "record_type",
        "action_kind",
        "cost_bucket",
        "gain_bucket",
        "recommendation",
        "applied_decision",
        "reason_code",
        "outcome_class",
        "count",
        "minimum_group_size",
    }
)
IDENTITY_FIELDS = ATOM_FIELDS - {"count"}
AGGREGATE_FIELDS = frozenset({"schema_version", "model_namespace", "atoms"})
ENUMS = {
    "record_type": frozenset({"decision", "outcome"}),
    "action_kind": frozenset(
        {
            "command",
            "file_read",
            "file_write",
            "generation",
            "llm",
            "model_call",
            "reasoning",
            "research",
            "review",
            "search",
            "subagent",
            "test",
            "tool",
            "verification",
            "unknown",
            "other",
        }
    ),
    "cost_bucket": frozenset({"low", "medium", "high", "unknown"}),
    "gain_bucket": frozenset({"low", "medium", "high", "unknown"}),
    "recommendation": frozenset({"allow", "deny", "unknown", "not_applicable"}),
    "applied_decision": frozenset({"allow", "deny", "unknown", "not_applicable"}),
    "reason_code": frozenset(
        {
            "APPROVED",
            "BUDGET_REJECTED",
            "DENY",
            "DUPLICATE_ACTION",
            "DUPLICATE_PENDING",
            "EXPECTED_GAIN_REJECTED",
            "FUNDED",
            "MARGINAL_ROI_REJECTED",
            "OTHER",
            "PARENT_BUDGET_REJECTED",
            "RECOMMEND_OVERRIDE",
            "SHADOW_OVERRIDE",
            "TARGET_REACHED",
            "UNSPECIFIED",
            "not_applicable",
        }
    ),
    "outcome_class": frozenset(
        {
            "verified_success",
            "verified_failure",
            "positive_reward",
            "non_positive_reward",
            "unknown",
            "not_applicable",
        }
    ),
}


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{name} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{name} keys must be strings")
    return value


def _closed_keys(value: Mapping[str, object], expected: frozenset[str], name: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ValidationError(f"{name} has unknown fields: {sorted(unknown)!r}")
    if missing:
        raise ValidationError(f"{name} is missing fields: {sorted(missing)!r}")


def _bounded_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValidationError(f"{name} must be an integer from 1 through 1000")
    return value


def parse_atom(value: object) -> dict[str, object]:
    """Validate and copy one frozen aggregate atom without extension fields."""
    atom = _mapping(value, "atom")
    _closed_keys(atom, ATOM_FIELDS, "atom")
    parsed: dict[str, object] = {}
    for field, allowed in ENUMS.items():
        candidate = atom[field]
        if not isinstance(candidate, str) or candidate not in allowed:
            raise ValidationError(f"atom.{field} is not an allowed value")
        parsed[field] = candidate
    parsed["count"] = _bounded_integer(atom["count"], "atom.count")
    parsed["minimum_group_size"] = _bounded_integer(
        atom["minimum_group_size"], "atom.minimum_group_size"
    )
    return parsed


def parse_aggregate_identity(value: object) -> dict[str, object]:
    """Validate immutable aggregate dimensions used by reviewed artifacts."""
    identity = _mapping(value, "aggregate identity")
    _closed_keys(identity, IDENTITY_FIELDS, "aggregate identity")
    parsed = parse_atom({**identity, "count": 1})
    del parsed["count"]
    return parsed


def aggregate_identity(atom: Mapping[str, object]) -> tuple[object, ...]:
    """Return the canonical dimensions that identify an aggregate, excluding volume."""
    return tuple(atom[field] for field in sorted(IDENTITY_FIELDS))


def parse_aggregate_document(value: object, namespaces: Iterable[str]) -> dict[str, object]:
    """Validate a present Ingress aggregate document, which must contain at least one atom.

    The caller represents an empty model prior by omitting its aggregate file entirely.
    """
    allowed_namespaces = frozenset(namespaces)
    document = _mapping(value, "aggregate document")
    _closed_keys(document, AGGREGATE_FIELDS, "aggregate document")
    if document["schema_version"] != "1.0":
        raise ValidationError("aggregate document has an unsupported schema_version")
    namespace = document["model_namespace"]
    if not isinstance(namespace, str) or namespace not in allowed_namespaces:
        raise ValidationError("aggregate document has an unregistered model_namespace")
    atoms = document["atoms"]
    if not isinstance(atoms, list):
        raise ValidationError("aggregate document atoms must be an array")
    if not atoms:
        raise ValidationError("present aggregate document atoms must be nonempty")
    return {
        "schema_version": "1.0",
        "model_namespace": namespace,
        "atoms": [parse_atom(atom) for atom in atoms],
    }


def parse_registry(value: object) -> tuple[str, ...]:
    """Return the exact, non-empty model namespace values from a closed registry."""
    registry = _mapping(value, "registry")
    _closed_keys(registry, frozenset({"schema_version", "models"}), "registry")
    if registry["schema_version"] != "1.0":
        raise ValidationError("registry has an unsupported schema_version")
    models = _mapping(registry["models"], "registry.models")
    if not models:
        raise ValidationError("registry.models must not be empty")
    namespaces = tuple(models.values())
    if not all(isinstance(namespace, str) and namespace for namespace in namespaces):
        raise ValidationError("registry models must map to non-empty strings")
    if len(set(namespaces)) != len(namespaces):
        raise ValidationError("registry model namespaces must be unique")
    return tuple(sorted(cast(str, namespace) for namespace in namespaces))


def parse_validation_artifacts(
    value: object, namespaces: Sequence[str]
) -> dict[str, dict[str, list[dict[str, object]]]]:
    """Validate model-scoped checked-in lifecycle approvals."""
    artifacts = _mapping(value, "validation artifacts")
    expected = frozenset({"schema_version", "models"})
    _closed_keys(artifacts, expected, "validation artifacts")
    if artifacts["schema_version"] != "1.0":
        raise ValidationError("validation artifacts have an unsupported schema_version")
    models = _mapping(artifacts["models"], "validation artifacts models")
    expected_namespaces = frozenset(namespaces)
    if set(models) != expected_namespaces:
        raise ValidationError("validation artifacts models must match the exact registry")
    parsed: dict[str, dict[str, list[dict[str, object]]]] = {}
    lifecycle_fields = frozenset({"supported", "validated", "promoted"})
    for namespace, lifecycle_value in models.items():
        lifecycle_mapping = _mapping(lifecycle_value, f"validation artifacts {namespace}")
        _closed_keys(lifecycle_mapping, lifecycle_fields, f"validation artifacts {namespace}")
        parsed[namespace] = {}
        for lifecycle in lifecycle_fields:
            values = lifecycle_mapping[lifecycle]
            if not isinstance(values, list):
                raise ValidationError(f"validation artifacts {lifecycle} must be an array")
            parsed[namespace][lifecycle] = [parse_aggregate_identity(item) for item in values]
    return parsed
