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
    identity = {key: value for key, value in aggregate.items() if key not in {"count", "lifecycle"}}

    namespace = "openai/gpt-5.6-sol"
    assert lifecycle_for(namespace, aggregate, {}) == "candidate"
    assert (
        lifecycle_for(namespace, aggregate, {namespace: {"supported": [identity]}}) == "supported"
    )
    assert (
        lifecycle_for(namespace, aggregate, {namespace: {"validated": [identity]}}) == "candidate"
    )
    assert (
        lifecycle_for(
            namespace,
            aggregate,
            {namespace: {"supported": [identity], "validated": [identity]}},
        )
        == "validated"
    )
    assert lifecycle_for(namespace, aggregate, {namespace: {"promoted": [identity]}}) == "candidate"
    assert (
        lifecycle_for(
            namespace,
            aggregate,
            {
                namespace: {
                    "supported": [identity],
                    "validated": [identity],
                    "promoted": [identity],
                }
            },
        )
        == "promoted"
    )


def test_validation_artifacts_cannot_advance_another_model_namespace() -> None:
    from validation.lifecycle import lifecycle_for

    aggregate = {"action_kind": "tool", "count": 1000}
    artifacts = {
        "openai/gpt-5.6-sol": {
            "supported": [
                {
                    "record_type": "decision",
                    "action_kind": "tool",
                    "cost_bucket": "low",
                    "gain_bucket": "medium",
                    "recommendation": "allow",
                    "applied_decision": "allow",
                    "reason_code": "APPROVED",
                    "outcome_class": "not_applicable",
                    "minimum_group_size": 1,
                }
            ]
        }
    }

    assert lifecycle_for("openai/gpt-5.6-terra", aggregate, artifacts) == "candidate"
