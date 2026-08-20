"""Validate the frozen contract, aggregate sources, and checked-in Commons pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.build_pack import (
    CommonsBuildError,
    canonical_bytes,
    compile_pack,
    git_source_environment,
)
from validation.schema import ATOM_FIELDS, ValidationError, aggregate_identity, parse_atom


class CommonsValidationError(ValueError):
    """Raised when checked-in Commons data is invalid, stale, or non-canonical."""


_PACK_FIELDS = frozenset(
    {
        "schema_version",
        "source_commit",
        "commons_revision",
        "compatibility",
        "models",
        "integrity",
    }
)
_NAMESPACES = frozenset(
    {
        "openai/gpt-5.6-sol",
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
    }
)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise CommonsValidationError(f"{name} must be an object")
    return value


def _closed(value: Mapping[str, object], expected: frozenset[str], name: str) -> None:
    if set(value) != expected:
        raise CommonsValidationError(f"{name} is not closed")


def validate_pack(value: object) -> dict[str, Any]:
    """Strictly validate a pack and verify its digest without third-party code."""
    pack = _mapping(value, "pack")
    _closed(pack, _PACK_FIELDS, "pack")
    if pack["schema_version"] != "1.0":
        raise CommonsValidationError("pack schema_version is unsupported")
    source_commit = pack["source_commit"]
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise CommonsValidationError("pack source_commit is invalid")
    revision = pack["commons_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise CommonsValidationError("pack commons_revision must be positive")
    compatibility = _mapping(pack["compatibility"], "pack compatibility")
    _closed(compatibility, frozenset({"evidence_envelope_schema_version"}), "pack compatibility")
    if compatibility["evidence_envelope_schema_version"] != "1.0":
        raise CommonsValidationError("pack compatibility is invalid")
    models = _mapping(pack["models"], "pack models")
    if set(models) != _NAMESPACES:
        raise CommonsValidationError("pack models are not the exact registry namespaces")
    for namespace, model in models.items():
        model_mapping = _mapping(model, f"pack model {namespace}")
        _closed(model_mapping, frozenset({"aggregates"}), f"pack model {namespace}")
        aggregates = model_mapping["aggregates"]
        if not isinstance(aggregates, list):
            raise CommonsValidationError("pack aggregates must be an array")
        identities: set[tuple[object, ...]] = set()
        for aggregate in aggregates:
            aggregate_mapping = _mapping(aggregate, "pack aggregate")
            if set(aggregate_mapping) != set(ATOM_FIELDS) | {"lifecycle"}:
                raise CommonsValidationError("pack aggregate is not closed")
            if aggregate_mapping.get("lifecycle") not in {
                "candidate",
                "supported",
                "validated",
                "promoted",
            }:
                raise CommonsValidationError("pack aggregate lifecycle is invalid")
            try:
                atom = parse_atom(
                    {key: value for key, value in aggregate_mapping.items() if key != "lifecycle"}
                )
            except ValidationError as error:
                raise CommonsValidationError(str(error)) from error
            identity = aggregate_identity(atom)
            if identity in identities:
                raise CommonsValidationError(
                    f"pack has duplicate aggregate dimensions: {namespace}"
                )
            identities.add(identity)
    integrity = _mapping(pack["integrity"], "pack integrity")
    _closed(integrity, frozenset({"sha256"}), "pack integrity")
    digest = integrity["sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise CommonsValidationError("pack integrity digest is invalid")
    payload = dict(pack)
    del payload["integrity"]
    if hashlib.sha256(canonical_bytes(payload)).hexdigest() != digest:
        raise CommonsValidationError("pack integrity digest does not match canonical payload")
    return dict(pack)


def validate_frozen_contract(root: Path) -> None:
    """Confirm that Task 1's frozen schema and registry bytes were not altered."""
    manifest_path = root / "schemas" / "commons-contract-v1.manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = _mapping(manifest, "contract manifest").get("sha256")
        hashes = _mapping(entries, "contract manifest sha256")
        for name, expected in hashes.items():
            if not isinstance(expected, str):
                raise CommonsValidationError("contract manifest digest is invalid")
            base = root / ("models" if name.startswith("canonical-model") else "schemas")
            actual = hashlib.sha256((base / name).read_bytes()).hexdigest()
            if actual != expected:
                raise CommonsValidationError(f"frozen contract digest changed: {name}")
        envelope = root / "schemas" / "commons-evidence-envelope-v1.json"
        recorded = (root / "schemas" / "commons-evidence-envelope-v1.sha256").read_text().strip()
        if hashlib.sha256(envelope.read_bytes()).hexdigest() != recorded:
            raise CommonsValidationError("frozen evidence envelope digest changed")
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise CommonsValidationError("invalid frozen contract") from error


def _validate_source_commit(root: Path, source_commit: str) -> None:
    """A pack references the committed source snapshot, not its generated dist commit."""
    if not (root / ".git").exists():
        return
    verified = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{source_commit}^{{commit}}"],
        capture_output=True,
        env=git_source_environment(root),
        text=True,
        check=False,
    )
    if verified.returncode != 0:
        raise CommonsValidationError("pack source_commit is not available in this repository")
    sources = ["models", "validation", "schemas", "tooling", "pyproject.toml"]
    current = subprocess.run(
        ["git", "-C", str(root), "diff", "--quiet", source_commit, "--", *sources],
        check=False,
        env=git_source_environment(root),
    )
    if current.returncode != 0:
        raise CommonsValidationError("pack source_commit does not match current source inputs")


def validate_repository(root: Path) -> None:
    """Prove the checked pack is canonical, digest-valid, and a clean source rebuild."""
    pack_path = root / "dist" / "commons-pack-v1.json"
    try:
        pack_bytes = pack_path.read_bytes()
        pack = validate_pack(json.loads(pack_bytes))
        source_commit = pack["source_commit"]
        revision = pack["commons_revision"]
        assert isinstance(source_commit, str)
        assert isinstance(revision, int)
        rebuilt = canonical_bytes(
            compile_pack(root, source_commit=source_commit, revision=revision)
        )
    except (OSError, json.JSONDecodeError, CommonsBuildError) as error:
        raise CommonsValidationError("Commons repository cannot be rebuilt") from error
    _validate_source_commit(root, source_commit)
    if pack_bytes != rebuilt:
        raise CommonsValidationError("checked pack is not the deterministic rebuild")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    try:
        validate_repository(arguments.root.resolve())
    except CommonsValidationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
