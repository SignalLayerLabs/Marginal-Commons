"""Lifecycle derivation from reviewed validation artifacts only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_LIFECYCLES = ("candidate", "supported", "validated", "promoted")


def lifecycle_for(
    namespace: str,
    aggregate: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Sequence[str]]],
) -> str:
    """Return the highest lifecycle explicitly approved for an aggregate.

    Counts deliberately do not participate.  An artifact may name an action
    kind for one exact model namespace. This keeps reviewed evidence from one
    public model from becoming a prior for another.
    """
    action_kind = aggregate.get("action_kind")
    if not isinstance(action_kind, str):
        return "candidate"
    namespace_artifacts = artifacts.get(namespace, {})
    status = "candidate"
    for lifecycle in _LIFECYCLES[1:]:
        values = namespace_artifacts.get(lifecycle, ())
        if action_kind not in values:
            break
        status = lifecycle
    return status
