# Marginal Commons

Marginal Commons is the public, Apache-2.0-licensed source of optional,
model-specific aggregate priors for MARGINAL. It stores aggregate dimensions only;
it does not store contribution envelopes, raw context, identifiers, timestamps,
paths, hashes, URLs, or free text.

An observation is **not a user**. Aggregate counts never advance an item beyond
`candidate`. Checked-in validation artifacts are required for `supported`,
`validated`, and `promoted`; every one of those states remains a prior only. Commons
has no local enforcement, promotion, trust, coverage, or Autopilot authority.

## Contents

- `models/<namespace>/aggregates.json` is the human-readable Ingress-compatible
  aggregate source for one exact registry namespace.
- `models/registry-v1.json` must exactly match the reviewed Task 1 canonical registry.
- `tooling/build_pack.py` creates the canonical, digest-protected pack.
- `tooling/validate_commons.py` checks frozen-contract hashes, schema closure, digest,
  source snapshot, and deterministic rebuild.

The checked-in sources intentionally contain no observations or validation artifacts.
They are empty initial sources, not synthetic evidence.

## Local verification

Use Python 3.10+ with the `dev` extras, then run:

```sh
ruff format --check .
ruff check .
mypy
pytest
python tooling/validate_commons.py
```

To build a pack from a committed source snapshot, pass its exact commit and a positive
revision:

```sh
python tooling/build_pack.py --source-commit <source-commit> --revision 1
```

See [architecture](docs/architecture.md), [privacy and threat model](docs/privacy-threat-model.md),
and [validation](docs/validation.md).
