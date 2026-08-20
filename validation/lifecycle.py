"""Lifecycle derivation from reviewed validation artifacts only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_LIFECYCLES = ("candidate", "supported", "validated", "promoted")


def lifecycle_for(aggregate: Mapping[str, Any], artifacts: Mapping[str, Sequence[str]]) -> str:
    """Return the highest lifecycle explicitly approved for an aggregate.

    Counts deliberately do not participate.  An artifact may name an action
    kind, which is useful for small reviewed fixtures and remains a bounded,
    non-free-text identifier under the frozen aggregate schema.
    """
    action_kind = aggregate.get("action_kind")
    if not isinstance(action_kind, str):
        return "candidate"
    status = "candidate"
    for lifecycle in _LIFECYCLES[1:]:
        values = artifacts.get(lifecycle, ())
        if action_kind not in values:
            break
        status = lifecycle
    return status
