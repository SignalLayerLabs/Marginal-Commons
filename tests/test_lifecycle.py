from __future__ import annotations


def test_validation_artifact_controls_lifecycle_without_count_promotion() -> None:
    """A volume-only implementation must not promote an aggregate."""
    from validation.lifecycle import lifecycle_for

    aggregate = {
        "record_type": "decision",
        "action_kind": "tool",
        "cost_bucket": "low",
        "gain_bucket": "medium",
        "recommendation": "allow",
        "applied_decision": "allow",
        "reason_code": "APPROVED",
        "outcome_class": "not_applicable",
        "count": 1000,
        "minimum_group_size": 1,
        "lifecycle": "candidate",
    }

    assert lifecycle_for(aggregate, {}) == "candidate"
    assert lifecycle_for(aggregate, {"supported": ["tool"]}) == "supported"
    assert lifecycle_for(aggregate, {"validated": ["tool"]}) == "candidate"
    assert lifecycle_for(aggregate, {"supported": ["tool"], "validated": ["tool"]}) == "validated"
    assert lifecycle_for(aggregate, {"promoted": ["tool"]}) == "candidate"
    assert (
        lifecycle_for(
            aggregate,
            {
                "supported": ["tool"],
                "validated": ["tool"],
                "promoted": ["tool"],
            },
        )
        == "promoted"
    )
