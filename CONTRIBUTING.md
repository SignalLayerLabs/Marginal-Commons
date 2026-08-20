# Contributing

Keep the Task 1 schema and digest files byte-for-byte frozen. Do not add a model,
aggregate dimension, extension field, identifier, free text, URL, path, hash, or
timestamp without a separately reviewed contract revision.

An aggregate source is scoped to its exact directory namespace and must retain the
Ingress document shape: `schema_version`, `model_namespace`, and `atoms`. Never add
production observations as examples or fixtures. Tests may use clearly synthetic
fixtures only.

Before opening a change, run the commands listed in the README. A lifecycle change
needs checked-in validation artifacts and regression coverage; count volume is never
evidence for advancement.
