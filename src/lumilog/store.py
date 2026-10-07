"""SQLite event store. Uses only the standard library."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .parser import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    minute     TEXT NOT NULL,
    level      TEXT NOT NULL,
    host       TEXT NOT NULL,
    event      TEXT NOT NULL,
    msgid      TEXT,
    msisdn     TEXT,
    provider   TEXT,
    status     TEXT,
    error      TEXT,
    latency_ms INTEGER,
    depth      INTEGER,
    attempt    INTEGER,
    raw        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_minute ON events(minute, event);
CREATE INDEX IF NOT EXISTS ix_events_msgid ON events(msgid);
"""


def connect(db: Path | str = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def load(con: sqlite3.Connection, events: list[Event]) -> int:
    rows = [
        (
            e.ts.isoformat(sep=" ", timespec="milliseconds"),
            e.ts.strftime("%Y-%m-%d %H:%M"),
            e.level, e.host, e.event, e.msgid, e.msisdn, e.provider,
            e.status, e.error, e.latency_ms, e.depth, e.attempt, e.raw,
        )
        for e in events
    ]
    con.executemany(
        "INSERT INTO events (ts, minute, level, host, event, msgid, msisdn, provider, status, error,"
        " latency_ms, depth, attempt, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    return len(rows)


def time_range(con: sqlite3.Connection) -> tuple[str | None, str | None]:
    row = con.execute("SELECT MIN(ts), MAX(ts) FROM events").fetchone()
    return row[0], row[1]
