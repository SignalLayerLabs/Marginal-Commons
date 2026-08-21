from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_commons import ATOM, _git, _write_sources


def test_repository_validation_detects_a_tampered_pack_and_rebuilds_it(tmp_path: Path) -> None:
    from tooling.build_pack import canonical_bytes, compile_pack
    from tooling.validate_commons import CommonsValidationError, validate_repository

    source_commit = _write_sources(tmp_path, [ATOM])
    output = tmp_path / "dist" / "commons-pack-v1.json"
    output.parent.mkdir()
    output.write_bytes(
        canonical_bytes(compile_pack(tmp_path, source_commit=source_commit, revision=1))
    )

    validate_repository(tmp_path)

    tampered = json.loads(output.read_text())
    tampered["models"]["openai/gpt-5.6-sol"]["aggregates"][0]["count"] = 2
    output.write_text(json.dumps(tampered))
    with pytest.raises(CommonsValidationError, match="digest"):
        validate_repository(tmp_path)


def test_cli_validates_current_committed_sources_without_dist_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tooling.build_pack import canonical_bytes, compile_pack
    from tooling.validate_commons import main

    source_commit = _write_sources(tmp_path, [ATOM])
    output = tmp_path / "dist" / "commons-pack-v1.json"
    output.parent.mkdir()
    output.write_bytes(
        canonical_bytes(compile_pack(tmp_path, source_commit=source_commit, revision=1))
    )

    aggregate_path = tmp_path / "models" / "openai/gpt-5.6-sol" / "aggregates.json"
    aggregate = json.loads(aggregate_path.read_text())
    aggregate["atoms"][0]["count"] = 2
    aggregate_path.write_text(json.dumps(aggregate))
    _git(tmp_path, "add", "models")
    _git(tmp_path, "commit", "-qm", "new anonymous contribution")

    monkeypatch.setattr(
        "sys.argv",
        ["validate_commons.py", "--root", str(tmp_path)],
    )

    assert main() == 0
