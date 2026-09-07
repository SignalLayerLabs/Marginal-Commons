from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "openai/gpt-6-astra",
)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text())


def _atom() -> dict[str, object]:
    return {
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


def _envelope() -> dict[str, object]:
    return {"schema_version": "1.0", "model_namespace": NAMESPACES[0], "atoms": [_atom()]}


def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(schema_name))


def _assert_invalid(validator: Draft202012Validator, payload: object) -> None:
    with pytest.raises(ValidationError):
        validator.validate(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"canary": "customer-acme"}),
        lambda value: value.update({"url": "https://example.invalid/private"}),
        lambda value: value.update({"path": "/private/customer/acme"}),
        lambda value: value.update({"sha256": "a" * 64}),
        lambda value: value["atoms"][0].update({"metadata": {"canary": "customer-acme"}}),
        lambda value: value["atoms"][0].update({"url": "https://example.invalid/private"}),
        lambda value: value["atoms"][0].update({"path": "/private/customer/acme"}),
        lambda value: value["atoms"][0].update({"sha256": "a" * 64}),
        lambda value: value.update({"model_namespace": "openai/gpt-5.6-sol-custom"}),
        lambda value: value["atoms"][0].update({"action_kind": "arbitrary"}),
        lambda value: value["atoms"][0].update({"count": 1001}),
        lambda value: value["atoms"][0].update({"minimum_group_size": 1001}),
        lambda value: value.update({"atoms": []}),
    ],
)
def test_commons_rejects_unsafe_or_open_contribution_envelopes(mutate: object) -> None:
    payload = _envelope()
    mutate(payload)  # type: ignore[operator]
    _assert_invalid(_validator("commons-evidence-envelope-v1.json"), payload)


def test_commons_accepts_only_exact_registry_entries() -> None:
    registry = json.loads((ROOT / "models" / "canonical-model-registry-v1.json").read_text())
    assert registry == {
        "schema_version": "1.0",
        "models": {
            "gpt-6-astra": "openai/gpt-6-astra",
            "gpt-5.6-sol": "openai/gpt-5.6-sol",
            "gpt-5.6-terra": "openai/gpt-5.6-terra",
            "gpt-5.6-luna": "openai/gpt-5.6-luna",
        },
    }


def test_commons_contract_manifest_detects_schema_and_registry_drift() -> None:
    envelope_digest = (ROOT / "schemas" / "commons-evidence-envelope-v1.sha256").read_text().strip()
    assert hashlib.sha256(
        (ROOT / "schemas" / "commons-evidence-envelope-v1.json").read_bytes()
    ).hexdigest() == envelope_digest
    manifest = json.loads((ROOT / "schemas" / "commons-contract-v1.manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        base = ROOT / ("models" if name.startswith("canonical-model") else "schemas")
        assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected


def test_commons_pack_is_closed_and_model_partitioned() -> None:
    pack = {
        "schema_version": "1.0",
        "source_commit": "a" * 40,
        "commons_revision": 1,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": {
            namespace: {"aggregates": [{**_atom(), "lifecycle": "candidate"}]}
            for namespace in NAMESPACES
        },
        "integrity": {"sha256": "b" * 64},
    }
    validator = _validator("commons-pack-v1.json")
    validator.validate(pack)
    for mutation in (
        lambda value: value.update({"metadata": "customer-acme"}),
        lambda value: value.update({"source_commit": "A" * 40}),
        lambda value: value["compatibility"].update({"url": "https://example.invalid"}),
        lambda value: value["models"].update({"custom/model": {"aggregates": []}}),
        lambda value: value["integrity"].update({"sha256": "b" * 63}),
    ):
        candidate = copy.deepcopy(pack)
        mutation(candidate)
        _assert_invalid(validator, candidate)


def test_commons_pack_accepts_a_pre_astra_model_set() -> None:
    pack = {
        "schema_version": "1.0",
        "source_commit": "a" * 40,
        "commons_revision": 1,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": {
            namespace: {"aggregates": []}
            for namespace in NAMESPACES
            if namespace != "openai/gpt-6-astra"
        },
        "integrity": {"sha256": "b" * 64},
    }

    _validator("commons-pack-v1.json").validate(pack)


@pytest.mark.parametrize("key", ["a" * 31, "a" * 65, "a" * 32 + "+", "a" * 31 + "="])
def test_commons_idempotency_key_is_separate_and_base64url(key: str) -> None:
    assert IDEMPOTENCY_KEY_PATTERN.fullmatch(key) is None


@pytest.mark.parametrize("key", ["a" * 32, "_" * 64])
def test_commons_accepts_base64url_idempotency_key_boundary_lengths(key: str) -> None:
    assert IDEMPOTENCY_KEY_PATTERN.fullmatch(key) is not None


def test_idempotency_key_is_not_persistable_as_envelope_json() -> None:
    _assert_invalid(
        _validator("commons-evidence-envelope-v1.json"),
        {**_envelope(), "Idempotency-Key": "a" * 32},
    )
