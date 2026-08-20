from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_commons import ATOM, NAMESPACES

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit_source(root: Path, atoms: list[dict[str, object]] | None = None) -> str:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Commons test")
    for name in (
        "commons-contract-v1.manifest.json",
        "commons-evidence-envelope-v1.json",
        "commons-evidence-envelope-v1.sha256",
        "commons-pack-v1.json",
    ):
        destination = root / "schemas" / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "schemas" / name, destination)
    registry = (ROOT / "models" / "canonical-model-registry-v1.json").read_text()
    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "canonical-model-registry-v1.json").write_text(registry)
    (root / "models" / "registry-v1.json").write_text(registry)
    if atoms is not None:
        aggregate_path = root / "models" / NAMESPACES[0] / "aggregates.json"
        aggregate_path.parent.mkdir(parents=True)
        aggregate_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "model_namespace": NAMESPACES[0],
                    "atoms": atoms,
                }
            )
        )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source")
    return _git(root, "rev-parse", "HEAD")


def _commit_change(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source update")
    return _git(root, "rev-parse", "HEAD")


def test_absent_source_becomes_empty_then_accepts_first_ingress_document(tmp_path: Path) -> None:
    from tooling.build_pack import compile_pack

    initial = _commit_source(tmp_path)
    empty_pack = compile_pack(tmp_path, source_commit=initial, revision=1)
    assert empty_pack["models"][NAMESPACES[0]]["aggregates"] == []

    aggregate_path = tmp_path / "models" / NAMESPACES[0] / "aggregates.json"
    aggregate_path.parent.mkdir(parents=True)
    aggregate_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model_namespace": NAMESPACES[0],
                "atoms": [ATOM],
            }
        )
    )
    first_ingress_commit = _commit_change(tmp_path)
    populated_pack = compile_pack(tmp_path, source_commit=first_ingress_commit, revision=2)

    assert populated_pack["models"][NAMESPACES[0]]["aggregates"] == [
        {**ATOM, "lifecycle": "candidate"}
    ]


def test_lifecycle_artifact_requires_the_complete_aggregate_identity() -> None:
    from validation.lifecycle import lifecycle_for

    identity = {key: value for key, value in ATOM.items() if key != "count"}
    artifacts = {
        NAMESPACES[0]: {
            "supported": [identity],
            "validated": [identity],
            "promoted": [identity],
        }
    }
    unrelated_tool = {**ATOM, "cost_bucket": "high", "count": 1000}

    assert lifecycle_for(NAMESPACES[0], ATOM, artifacts) == "promoted"
    assert lifecycle_for(NAMESPACES[0], unrelated_tool, artifacts) == "candidate"


def test_builder_rejects_duplicate_dimension_tuples_at_maximum_count(tmp_path: Path) -> None:
    from tooling.build_pack import CommonsBuildError, compile_pack

    source_commit = _commit_source(tmp_path, [{**ATOM, "count": 1000}, {**ATOM, "count": 1000}])

    with pytest.raises(CommonsBuildError, match="duplicate"):
        compile_pack(tmp_path, source_commit=source_commit, revision=1)


def test_builder_reads_the_claimed_commit_not_a_mutated_worktree(tmp_path: Path) -> None:
    from tooling.build_pack import compile_pack

    source_commit = _commit_source(tmp_path, [ATOM])
    aggregate_path = tmp_path / "models" / NAMESPACES[0] / "aggregates.json"
    aggregate = json.loads(aggregate_path.read_text())
    aggregate["atoms"][0]["count"] = 999
    aggregate_path.write_text(json.dumps(aggregate))

    pack = compile_pack(tmp_path, source_commit=source_commit, revision=1)

    assert pack["models"][NAMESPACES[0]]["aggregates"][0]["count"] == 1


def test_builder_rejects_an_untracked_aggregate_input(tmp_path: Path) -> None:
    from tooling.build_pack import CommonsBuildError, compile_pack

    source_commit = _commit_source(tmp_path)
    aggregate_path = tmp_path / "models" / NAMESPACES[0] / "aggregates.json"
    aggregate_path.parent.mkdir(parents=True)
    aggregate_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model_namespace": NAMESPACES[0],
                "atoms": [ATOM],
            }
        )
    )

    with pytest.raises(CommonsBuildError, match="untracked"):
        compile_pack(tmp_path, source_commit=source_commit, revision=1)


def test_builder_rejects_a_symlinked_source_input(tmp_path: Path) -> None:
    from tooling.build_pack import CommonsBuildError, compile_pack

    source_commit = _commit_source(tmp_path)
    registry = tmp_path / "models" / "registry-v1.json"
    registry.unlink()
    registry.symlink_to("canonical-model-registry-v1.json")

    with pytest.raises(CommonsBuildError, match="symlink"):
        compile_pack(tmp_path, source_commit=source_commit, revision=1)
