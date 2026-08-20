"""Build a closed, deterministic Commons prior pack from a Git source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.lifecycle import lifecycle_for
from validation.schema import (
    ValidationError,
    aggregate_identity,
    parse_aggregate_document,
    parse_registry,
    parse_validation_artifacts,
)


class CommonsBuildError(ValueError):
    """Raised when source data cannot safely become a Commons pack."""


def git_source_environment(root: Path) -> dict[str, str]:
    """Return the fixed environment for every Git source/provenance operation."""
    return {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "HOME": str(root / ".git-source-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }


def canonical_bytes(value: object) -> bytes:
    """Encode the sole Commons serialization form: sorted UTF-8 JSON, no whitespace."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _read_json_bytes(content: bytes, name: str) -> object:
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CommonsBuildError(f"invalid JSON at {name}") from error


class _GitSource:
    """Read only regular, tracked source bytes from one immutable Git tree."""

    def __init__(self, root: Path, commit: str) -> None:
        self.root = root
        self.commit = commit
        self._run("rev-parse", "--verify", f"{commit}^{{commit}}")
        self._reject_untracked_inputs()

    def _run(self, *arguments: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=False,
            capture_output=True,
            env=git_source_environment(self.root),
        )
        if result.returncode != 0:
            raise CommonsBuildError("claimed source_commit is not available in this repository")
        return result.stdout

    def _reject_untracked_inputs(self) -> None:
        status = self._run("status", "--porcelain", "--untracked-files=all").decode("utf-8")
        for line in status.splitlines():
            path = line[3:]
            if line.startswith("?? ") and (
                path.startswith("models/")
                or path.startswith("schemas/")
                or path == "validation/artifacts-v1.json"
            ):
                raise CommonsBuildError(f"untracked source input: {path}")

    def read_optional(self, path: str) -> bytes | None:
        entry = self._run("ls-tree", "-z", self.commit, "--", path)
        if not entry:
            return None
        metadata, separator, listed_path = entry.rstrip(b"\0").partition(b"\t")
        if not separator or listed_path.decode("utf-8") != path:
            raise CommonsBuildError(f"invalid source tree entry: {path}")
        try:
            mode, kind, _object_id = metadata.decode("ascii").split(" ", 2)
        except ValueError as error:
            raise CommonsBuildError(f"invalid source tree entry: {path}") from error
        if mode == "120000":
            raise CommonsBuildError(f"symlink source input: {path}")
        if mode != "100644" or kind != "blob":
            raise CommonsBuildError(f"source input is not a regular file: {path}")
        working_path = self.root / path
        if working_path.is_symlink():
            raise CommonsBuildError(f"symlink source input: {path}")
        return self._run("show", f"{self.commit}:{path}")

    def read_required(self, path: str) -> bytes:
        content = self.read_optional(path)
        if content is None:
            raise CommonsBuildError(f"missing tracked source input: {path}")
        return content


def _artifacts(
    source: _GitSource, namespaces: tuple[str, ...]
) -> dict[str, dict[str, list[dict[str, object]]]]:
    content = source.read_optional("validation/artifacts-v1.json")
    if content is None:
        return {}
    try:
        return parse_validation_artifacts(
            _read_json_bytes(content, "validation artifacts"), namespaces
        )
    except ValidationError as error:
        raise CommonsBuildError(str(error)) from error


def _verify_frozen_contract(source: _GitSource) -> None:
    """Verify Task 1 contract bytes from the claimed source tree, never the worktree."""
    manifest = _read_json_bytes(
        source.read_required("schemas/commons-contract-v1.manifest.json"),
        "schemas/commons-contract-v1.manifest.json",
    )
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "sha256"}:
        raise CommonsBuildError("frozen contract manifest is not closed")
    digests = manifest["sha256"]
    if not isinstance(digests, dict):
        raise CommonsBuildError("frozen contract manifest digests are invalid")
    for name, expected in digests.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            raise CommonsBuildError("frozen contract manifest digests are invalid")
        base = "models" if name.startswith("canonical-model") else "schemas"
        actual = hashlib.sha256(source.read_required(f"{base}/{name}")).hexdigest()
        if actual != expected:
            raise CommonsBuildError(f"frozen contract digest changed: {name}")
    envelope = source.read_required("schemas/commons-evidence-envelope-v1.json")
    recorded = (
        source.read_required("schemas/commons-evidence-envelope-v1.sha256").decode("ascii").strip()
    )
    if hashlib.sha256(envelope).hexdigest() != recorded:
        raise CommonsBuildError("frozen evidence envelope digest changed")


def compile_pack(root: Path, *, source_commit: str, revision: int) -> dict[str, Any]:
    """Compile registered sources from ``source_commit``, never mutable file bytes."""
    if len(source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in source_commit
    ):
        raise CommonsBuildError("source_commit must be a lower-case 40-character SHA-1")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise CommonsBuildError("revision must be a positive integer")
    try:
        source = _GitSource(root, source_commit)
        _verify_frozen_contract(source)
        registry_value = _read_json_bytes(
            source.read_required("models/registry-v1.json"), "models/registry-v1.json"
        )
        canonical_value = _read_json_bytes(
            source.read_required("models/canonical-model-registry-v1.json"),
            "models/canonical-model-registry-v1.json",
        )
        if registry_value != canonical_value:
            raise CommonsBuildError(
                "registry-v1.json must exactly match the reviewed canonical registry"
            )
        namespaces = parse_registry(registry_value)
        artifacts = _artifacts(source, namespaces)
        models: dict[str, dict[str, list[dict[str, object]]]] = {}
        for namespace in namespaces:
            source_path = f"models/{namespace}/aggregates.json"
            content = source.read_optional(source_path)
            if content is None:
                models[namespace] = {"aggregates": []}
                continue
            document = parse_aggregate_document(_read_json_bytes(content, source_path), namespaces)
            if document["model_namespace"] != namespace:
                raise CommonsBuildError(f"aggregate namespace does not match path: {namespace}")
            atoms = document["atoms"]
            assert isinstance(atoms, list)
            aggregates: list[dict[str, object]] = []
            identities: set[tuple[object, ...]] = set()
            for atom in atoms:
                assert isinstance(atom, dict)
                identity = aggregate_identity(atom)
                if identity in identities:
                    raise CommonsBuildError(f"duplicate aggregate dimensions: {namespace}")
                identities.add(identity)
                aggregates.append({**atom, "lifecycle": lifecycle_for(namespace, atom, artifacts)})
            aggregates.sort(key=canonical_bytes)
            models[namespace] = {"aggregates": aggregates}
    except ValidationError as error:
        raise CommonsBuildError(str(error)) from error
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "source_commit": source_commit,
        "commons_revision": revision,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": models,
    }
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return {**payload, "integrity": {"sha256": digest}}


def write_pack(
    root: Path, *, source_commit: str, revision: int, output: Path | None = None
) -> Path:
    """Compile and atomically replace the checked-in pack path."""
    destination = output or root / "dist" / "commons-pack-v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        canonical_bytes(compile_pack(root, source_commit=source_commit, revision=revision))
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        write_pack(
            arguments.root.resolve(),
            source_commit=arguments.source_commit,
            revision=arguments.revision,
            output=arguments.output,
        )
    except CommonsBuildError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
