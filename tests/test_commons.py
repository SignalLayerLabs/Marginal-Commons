from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

ATOM = {
    "record_type": "decision",
    "action_kind": "tool",
    "cost_bucket": "low",
    "gain_bucket": "medium",
    "recommendation": "allow",
    "applied_decision": "allow",
    "reason_code": "APPROVED",
    "outcome_class": "not_applicable",
    "count": 1,
    "minimum_group_size": 1,
}
NAMESPACES = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
)


def _write_sources(root: Path, sol_atoms: list[dict[str, object]]) -> None:
    registry = {
        "schema_version": "1.0",
        "models": {
            "gpt-5.6-sol": NAMESPACES[0],
            "gpt-5.6-terra": NAMESPACES[1],
            "gpt-5.6-luna": NAMESPACES[2],
        },
    }
    (root / "models").mkdir()
    (root / "models" / "registry-v1.json").write_text(json.dumps(registry))
    (root / "models" / "canonical-model-registry-v1.json").write_text(json.dumps(registry))
    for namespace in NAMESPACES:
        destination = root / "models" / namespace / "aggregates.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "model_namespace": namespace,
                    "atoms": sol_atoms if namespace == NAMESPACES[0] else [],
                }
            )
        )


def test_strict_aggregate_validation_rejects_recursive_poisoning() -> None:
    from validation.schema import ValidationError, parse_aggregate_document

    document = {
        "schema_version": "1.0",
        "model_namespace": NAMESPACES[0],
        "atoms": [{**ATOM, "metadata": {"canary": "customer-acme"}}],
    }

    with pytest.raises(ValidationError, match="unknown"):
        parse_aggregate_document(document, NAMESPACES)


def test_pack_builder_keeps_namespaces_isolated_and_stable(tmp_path: Path) -> None:
    from tooling.build_pack import canonical_bytes, compile_pack

    _write_sources(tmp_path, [{**ATOM, "count": 999}])
    first = compile_pack(tmp_path, source_commit="a" * 40, revision=1)
    second = compile_pack(tmp_path, source_commit="a" * 40, revision=1)

    assert canonical_bytes(first) == canonical_bytes(second)
    assert first["models"][NAMESPACES[0]]["aggregates"] == [
        {**ATOM, "count": 999, "lifecycle": "candidate"}
    ]
    assert first["models"][NAMESPACES[1]]["aggregates"] == []
    assert first["models"][NAMESPACES[2]]["aggregates"] == []
    payload = copy.deepcopy(first)
    del payload["integrity"]
    assert first["integrity"]["sha256"] == hashlib.sha256(canonical_bytes(payload)).hexdigest()


def test_pack_builder_rejects_a_namespace_mismatch_before_compilation(tmp_path: Path) -> None:
    from tooling.build_pack import CommonsBuildError, compile_pack

    _write_sources(tmp_path, [])
    aggregate_path = tmp_path / "models" / NAMESPACES[0] / "aggregates.json"
    aggregate = json.loads(aggregate_path.read_text())
    aggregate["model_namespace"] = NAMESPACES[1]
    aggregate_path.write_text(json.dumps(aggregate))

    with pytest.raises(CommonsBuildError, match="namespace"):
        compile_pack(tmp_path, source_commit="a" * 40, revision=1)
