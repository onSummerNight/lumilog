# LumiLog

Incident analysis for SMS gateway logs. Scope: `docs/CONTEXT.md`. Usage: `README.md`.

**Your role:** Executor. Build what the locked context says, one verified step at a time. Task briefs arrive in `docs/BRIEF.md` from the consultant session in `../hq`.

## How to work

Adapted from the Karpathy guidelines (https://github.com/multica-ai/andrej-karpathy-skills, MIT).

1. **Think before coding.** State your assumptions. If a request has two readings, ask instead of guessing. Say so when a simpler way exists.
2. **Simplicity first.** Write the minimum that solves the task. No speculative features, abstractions or options nobody asked for.
3. **Surgical changes.** Touch only what the task needs. Match the existing style. Don't refactor or tidy neighbouring code. Remove only what your own change orphaned.
4. **Goal-driven.** Turn the task into a check you can run (a test, a command, an output) and loop until it passes. Report what you verified and what you did not.

## Scope lock

- `docs/CONTEXT.md` is the agreed scope. If its Status is DRAFT or the file is missing, run the `/kickoff` interview before building anything.
- Once LOCKED, ideas outside it go to **Later** in `docs/PROGRESS.md`, not into the work. Scope changes only through `/decide`, with an explicit yes from the user.

## State files (keep them short)

- `docs/PROGRESS.md`: current state as Done / Now / Next / Later / Blockers. Rewritten each save, never appended. About 40 lines at most.
- `docs/LOG.md`: append-only, one line per action: `YYYY-MM-DD HH:MM | who | what | result`.
- `docs/DECISIONS.md`: append-only: date, decision, why, alternatives rejected.

## Token discipline

- Begin a session with `/continue-progress`, end it with `/save-progress`, then `/clear`.
- Read only the files the task needs. Don't re-read what is already in context. No repo-wide scans unless asked.
- Answer briefly. Don't recap what the user can already see. A plan should be shorter than the change it describes.

## Rules

- **Clean room.** Nothing from an employer or client: no code, configs, hostnames, IPs, log samples or names. Public specs and synthetic data only.
- **Honest.** Real dates, real status, real results. Never say tests pass without running them.
- **Git.** Small commits with clear messages. Keep the `Co-Authored-By: Claude` trailer Claude Code adds. Ask before pushing or publishing anything.
- **Secrets.** Never commit keys, tokens or `.env` files.
