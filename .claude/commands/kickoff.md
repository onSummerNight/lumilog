---
description: "Agree the project scope with the user, then lock it in docs/CONTEXT.md"
argument-hint: "[idea]"
disable-model-invocation: true
---
Agree what we are building, then lock it. Write no code in this command.

1. If `docs/CONTEXT.md` exists as a DRAFT, read it and present it in under 12 lines. Otherwise start from the user's idea: $ARGUMENTS
2. Interview the user, at most 3 questions per turn, until each of these is clear:
   problem and who has it; what the first version does (3 to 5 bullets); non-goals; the check that proves it works; stack; constraints.
   Offer your own recommendation with each question. Push back when something is vague or too big for a first version.
3. Write `docs/CONTEXT.md` with: Status, Problem, Users, Scope v1, Non-goals, Success check, Stack, Constraints, Open questions.
4. Show it and ask: "Lock this?" Only after a clear yes, set `Status: LOCKED <date>`.
5. Then write `docs/PROGRESS.md` (first three steps under Next) and append one line to `docs/LOG.md`.
