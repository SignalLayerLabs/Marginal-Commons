# Validation and release procedure

1. Review the aggregate source and, if lifecycle advancement is proposed, add the
   required checked-in validation artifacts and regression tests. Counts alone cannot
   justify a transition.
2. Commit all source inputs first. Record that commit as the pack `source_commit`.
   Source inputs are only regular tracked Git-tree bytes: the frozen schemas and
   registry, present aggregate files, and a present validation artifact file. The build
   rejects untracked and symlinked inputs, ignores mutable working-tree file bytes, and
   runs every source/provenance Git command with `GIT_NO_REPLACE_OBJECTS=1` in a fixed,
   sanitized environment. Local `git replace` refs therefore cannot change the claimed
   source tree.
3. Build the pack with that explicit source commit and a positive revision, then commit
   the generated `dist` update separately. This avoids an impossible self-referential
   Git commit hash: the pack describes its prior source commit, while the follow-up
   commit adds only the derived pack.
4. Run `python tooling/validate_commons.py`. It checks the frozen contract digests,
   closed source and pack schemas, namespace isolation, lifecycle derivation, digest,
   source snapshot, and byte-for-byte rebuild.

No current aggregate source or validation artifact is production evidence; the initial
sources are intentionally absent/empty. The resulting pack remains a prior only and
cannot enable or alter MARGINAL enforcement.
