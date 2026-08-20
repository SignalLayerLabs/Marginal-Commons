# Architecture

Ingress writes only closed aggregate documents to `models/<model_namespace>/aggregates.json`.
Commons validates each document with the standard library and reads the exact reviewed
registry. A document whose embedded namespace differs from its path is rejected. No
source is merged across namespaces.

The builder assigns `candidate` by default. It may step through `supported`,
`validated`, and `promoted` only when matching reviewed validation artifacts for every
preceding transition are checked in. Atom counts are deliberately ignored by lifecycle
derivation.

The builder emits canonical sorted JSON and hashes the canonical payload with the
`integrity` member omitted. The pack records the input source commit and a positive
Commons revision. The generated pack is a read-only prior for a matching model
namespace; it is not local enforcement authority.
