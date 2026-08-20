# Privacy and threat model

Commons is not telemetry. An observation is not a user, and the repository does not
model users, contributors, sessions, identities, devices, projects, repositories, or
time. It persists only bounded counts across closed aggregate dimensions for exact
public model namespaces.

The boundary rejects recursive unknown fields and arbitrary strings, including free
text, metadata objects, URLs, paths, hashes, timestamps, and unregistered model names.
The contributor retry token is an Ingress HTTP header only; it does not belong in a
Commons source or pack.

Threats addressed here include cardinality poisoning, namespace confusion, forged
lifecycle status, stale generated output, and pack tampering. Strict parsing, exact
registry comparison, per-path namespace checks, artifact-only lifecycle derivation,
canonical rebuild comparison, and a SHA-256 integrity digest provide the respective
controls. These controls do not make Commons a local policy authority: every state is
only a prior, and local verified evidence remains authoritative.
