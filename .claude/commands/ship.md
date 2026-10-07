---
description: "Pre-release checks, version, commit and tag"
argument-hint: "[version]"
disable-model-invocation: true
---
Prepare a release. Version or note: $ARGUMENTS

1. Run the full test suite. Stop on any failure.
2. Check the README: every command in it works and matches current behaviour.
3. Scan tracked files for secrets and for anything that breaks the clean-room rule (hostnames, IPs, real names, real data). Report hits.
4. Bump the version, commit, and tag it.
5. Show what would be pushed and ask before pushing.
6. Update `docs/PROGRESS.md` and append one line to `docs/LOG.md`.
