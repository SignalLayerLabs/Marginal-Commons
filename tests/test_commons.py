from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
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
    "openai/gpt-6-astra",
)
ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_sources(root: Path, sol_atoms: list[dict[str, object]]) -> str:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Commons test")
    registry = (ROOT / "models" / "canonical-model-registry-v1.json").read_text()
    (root / "models").mkdir()
    (root / "models" / "registry-v1.json").write_text(registry)
    (root / "models" / "canonical-model-registry-v1.json").write_text(registry)
    if sol_atoms:
        destination = root / "models" / NAMESPACES[0] / "aggregates.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "model_namespace": NAMESPACES[0],
                    "atoms": sol_atoms,
                }
            )
        )
    for name in (
        "commons-contract-v1.manifest.json",
        "commons-evidence-envelope-v1.json",
        "commons-evidence-envelope-v1.sha256",
        "commons-pack-v1.json",
    ):
        destination = root / "schemas" / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "schemas" / name, destination)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source")
    return _git(root, "rev-parse", "HEAD")


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

    source_commit = _write_sources(tmp_path, [{**ATOM, "count": 999}])
    first = compile_pack(tmp_path, source_commit=source_commit, revision=1)
    second = compile_pack(tmp_path, source_commit=source_commit, revision=1)

    assert canonical_bytes(first) == canonical_bytes(second)
    assert first["models"][NAMESPACES[0]]["aggregates"] == [
        {**ATOM, "count": 999, "lifecycle": "candidate"}
    ]
    assert first["models"][NAMESPACES[1]]["aggregates"] == []
    assert first["models"][NAMESPACES[2]]["aggregates"] == []
    assert first["models"][NAMESPACES[3]]["aggregates"] == []
    payload = copy.deepcopy(first)
    del payload["integrity"]
    assert first["integrity"]["sha256"] == hashlib.sha256(canonical_bytes(payload)).hexdigest()


def test_pack_builder_rejects_a_namespace_mismatch_before_compilation(tmp_path: Path) -> None:
    from tooling.build_pack import CommonsBuildError, compile_pack

    _write_sources(tmp_path, [ATOM])
    aggregate_path = tmp_path / "models" / NAMESPACES[0] / "aggregates.json"
    aggregate = json.loads(aggregate_path.read_text())
    aggregate["model_namespace"] = NAMESPACES[1]
    aggregate_path.write_text(json.dumps(aggregate))
    _git(tmp_path, "add", "models")
    _git(tmp_path, "commit", "-qm", "namespace mismatch")
    source_commit = _git(tmp_path, "rev-parse", "HEAD")

    with pytest.raises(CommonsBuildError, match="namespace"):
        compile_pack(tmp_path, source_commit=source_commit, revision=1)
