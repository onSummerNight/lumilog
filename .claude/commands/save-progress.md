---
description: "Save the session: update progress, log, decisions and commit"
argument-hint: "[push]"
disable-model-invocation: true
---
Save this session so a fresh one can continue from the files alone.

1. If code changed, run the tests. Record the real result.
2. Rewrite `docs/PROGRESS.md` (Done / Now / Next / Later / Blockers), 40 lines at most.
3. Append to `docs/LOG.md` one line per meaningful action this session: `YYYY-MM-DD HH:MM | who | what | result`.
4. Append to `docs/DECISIONS.md` any decision made this session that is not recorded yet.
5. Commit everything with a clear message. Push only if the arguments say so: $ARGUMENTS
6. Reply with the commit hash and the next step, in 3 lines. Then suggest `/clear`.
