---
description: "Record a decision, and change the locked scope only with approval"
argument-hint: "<decision>"
disable-model-invocation: true
---
Record this decision: $ARGUMENTS

1. Append to `docs/DECISIONS.md`: date, decision, why, alternatives rejected. Keep it to 4 lines.
2. If it changes anything in `docs/CONTEXT.md`, show the exact lines you would change and ask for a yes first.
   After a yes, edit CONTEXT and add a `Changed: <date> <what>` line under Status.
3. Append one line to `docs/LOG.md`.
