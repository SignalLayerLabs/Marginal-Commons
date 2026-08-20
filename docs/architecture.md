# Architecture

Ingress creates a closed aggregate document at
`models/<model_namespace>/aggregates.json` only after the first contribution. Its absence
is the canonical empty source. Commons validates a present document with the standard
library and reads the exact reviewed registry. A document whose embedded namespace differs
from its path is rejected. No source is merged across namespaces.

The builder assigns `candidate` by default. It may step through `supported`,
`validated`, and `promoted` only when matching reviewed validation artifacts for the
same exact namespace and complete aggregate identity (every dimension except `count`)
are checked in for every preceding transition. Atom counts are deliberately ignored by
lifecycle derivation.

The builder reads regular, tracked input bytes from the exact Git tree identified by the
pack's `source_commit`; it rejects source symlinks and untracked source files. It emits
canonical sorted JSON and hashes the canonical payload with the `integrity` member
omitted. The generated pack is a read-only prior for a matching model namespace; it is
not local enforcement authority.
