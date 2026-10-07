---
description: "Resume work from the saved state"
argument-hint: "[focus]"
disable-model-invocation: true
---
Resume with the least reading possible.

1. Read `docs/CONTEXT.md`, `docs/PROGRESS.md`, and `docs/BRIEF.md` if it exists. Read only the last 15 lines of `docs/LOG.md`.
2. Run `git status --short` and `git log --oneline -5`.
3. If CONTEXT is not LOCKED, stop and tell the user to run `/kickoff`.
4. Reply in at most 8 lines: where we are, the next step, anything blocking. Extra instruction from the user: $ARGUMENTS
5. Wait for a go-ahead only if the next step is ambiguous or irreversible. Otherwise start on it.
