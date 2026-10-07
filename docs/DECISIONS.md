# Decisions

Append-only. Date, decision, why, alternatives rejected.

2026-10-07 | Detectors are deterministic; the model only investigates | testable numbers, low token cost | model reads raw logs
2026-10-07 | Offline investigator ships next to the Claude one | works with no key or cost, same tools | Claude only
2026-10-07 | SQLite from the standard library | no dependency, enough for log files | DuckDB
