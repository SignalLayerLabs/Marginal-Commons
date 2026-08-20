"""Build a closed, deterministic Commons prior pack from aggregate sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.lifecycle import lifecycle_for
from validation.schema import (
    ValidationError,
    parse_aggregate_document,
    parse_registry,
    parse_validation_artifacts,
)


class CommonsBuildError(ValueError):
    """Raised when source data cannot safely become a Commons pack."""


def canonical_bytes(value: object) -> bytes:
    """Encode the sole Commons serialization form: sorted UTF-8 JSON, no whitespace."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CommonsBuildError(f"invalid JSON at {path}") from error


def _artifacts(root: Path, namespaces: tuple[str, ...]) -> dict[str, dict[str, list[str]]]:
    path = root / "validation" / "artifacts-v1.json"
    if not path.exists():
        return {}
    try:
        return parse_validation_artifacts(_read_json(path), namespaces)
    except ValidationError as error:
        raise CommonsBuildError(str(error)) from error


def compile_pack(root: Path, *, source_commit: str, revision: int) -> dict[str, Any]:
    """Compile all registered model sources; no source may leak into another model."""
    if len(source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in source_commit
    ):
        raise CommonsBuildError("source_commit must be a lower-case 40-character SHA-1")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise CommonsBuildError("revision must be a positive integer")
    try:
        registry_path = root / "models" / "registry-v1.json"
        canonical_registry_path = root / "models" / "canonical-model-registry-v1.json"
        registry_value = _read_json(registry_path)
        canonical_value = _read_json(canonical_registry_path)
        if registry_value != canonical_value:
            raise CommonsBuildError(
                "registry-v1.json must exactly match the reviewed canonical registry"
            )
        namespaces = parse_registry(registry_value)
        artifacts = _artifacts(root, namespaces)
        models: dict[str, dict[str, list[dict[str, object]]]] = {}
        for namespace in namespaces:
            source_path = root / "models" / namespace / "aggregates.json"
            document = parse_aggregate_document(_read_json(source_path), namespaces)
            if document["model_namespace"] != namespace:
                raise CommonsBuildError(f"aggregate namespace does not match path: {namespace}")
            atoms = document["atoms"]
            assert isinstance(atoms, list)
            aggregates = []
            for atom in atoms:
                assert isinstance(atom, dict)
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
