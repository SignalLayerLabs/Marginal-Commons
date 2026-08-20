"""Lifecycle derivation from reviewed validation artifacts only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from validation.schema import aggregate_identity

_LIFECYCLES = ("candidate", "supported", "validated", "promoted")


def lifecycle_for(
    namespace: str,
    aggregate: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]],
) -> str:
    """Return the highest lifecycle explicitly approved for an aggregate.

    Counts deliberately do not participate. An artifact must match all frozen
    dimensions except count for one exact model namespace.
    """
    try:
        identity = aggregate_identity(aggregate)
    except KeyError:
        return "candidate"
    namespace_artifacts = artifacts.get(namespace, {})
    status = "candidate"
    for lifecycle in _LIFECYCLES[1:]:
        values = namespace_artifacts.get(lifecycle, ())
        if not any(aggregate_identity(item) == identity for item in values):
            break
        status = lifecycle
    return status
