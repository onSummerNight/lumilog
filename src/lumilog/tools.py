"""Query tools over the event store.

Used by both investigators. Every value returned is computed from the store
and every raw line is redacted, so tool output is safe to send to an LLM.
Time arguments are minute strings: 'YYYY-MM-DD HH:MM', start inclusive, end exclusive.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .redact import redact

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "search_logs",
        "description": "Return matching raw log lines (redacted), oldest first. Use to collect evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Window start 'YYYY-MM-DD HH:MM' (inclusive)"},
                "end": {"type": "string", "description": "Window end 'YYYY-MM-DD HH:MM' (exclusive)"},
                "host": {"type": "string"},
                "provider": {"type": "string"},
                "level": {"type": "string", "enum": ["INFO", "WARN", "ERROR"]},
                "event": {"type": "string", "enum": ["SUBMIT", "DLR", "RETRY", "QUEUE"]},
                "contains": {"type": "string", "description": "Substring the raw line must contain"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
        },
    },
    {
        "name": "error_stats",
        "description": "Submit volume, failures and failure rate in a window, grouped by provider, host or error.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "group_by": {"type": "string", "enum": ["provider", "host", "error"], "default": "provider"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "trace_message",
        "description": "All lines for one message id in time order (submit, retries, delivery report).",
        "input_schema": {
            "type": "object",
            "properties": {"msgid": {"type": "string"}},
            "required": ["msgid"],
        },
    },
    {
        "name": "slow_deliveries",
        "description": "Messages submitted in a window with the longest submit-to-delivery-report delay, "
                       "with both lines. Use for delivery report (DLR) delay incidents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "provider": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "compare_windows",
        "description": "Compare key metrics between window A (usually the incident) and window B (usually a normal period).",
        "input_schema": {
            "type": "object",
            "properties": {
                "a_start": {"type": "string"}, "a_end": {"type": "string"},
                "b_start": {"type": "string"}, "b_end": {"type": "string"},
                "provider": {"type": "string"},
                "host": {"type": "string"},
            },
            "required": ["a_start", "a_end", "b_start", "b_end"],
        },
    },
]


class Toolbox:
    def __init__(self, con: sqlite3.Connection, max_limit: int = 50):
        self.con = con
        self.max_limit = max_limit

    def call(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name and return a JSON string. Errors are returned, not raised."""
        fn = {
            "search_logs": self.search_logs,
            "error_stats": self.error_stats,
            "trace_message": self.trace_message,
            "slow_deliveries": self.slow_deliveries,
            "compare_windows": self.compare_windows,
        }.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool {name!r}"})
        try:
            return json.dumps(fn(**args), default=str)
        except TypeError as exc:
            return json.dumps({"error": f"bad arguments: {exc}"})
        except sqlite3.Error as exc:
            return json.dumps({"error": f"query failed: {exc}"})

    # -- tools -----------------------------------------------------------

    def search_logs(self, start: str | None = None, end: str | None = None, host: str | None = None,
                    provider: str | None = None, level: str | None = None, event: str | None = None,
                    contains: str | None = None, limit: int = 20) -> dict[str, Any]:
        where, params = self._filters(start, end, host=host, provider=provider)
        if level:
            where.append("level = ?"); params.append(level)
        if event:
            where.append("event = ?"); params.append(event)
        if contains:
            where.append("raw LIKE ?"); params.append(f"%{contains}%")
        clause = " AND ".join(where) or "1=1"
        limit = max(1, min(int(limit), self.max_limit))
        total = self.con.execute(f"SELECT COUNT(*) FROM events WHERE {clause}", params).fetchone()[0]
        rows = self.con.execute(
            f"SELECT raw FROM events WHERE {clause} ORDER BY ts LIMIT ?", [*params, limit]
        ).fetchall()
        return {"total_matches": total, "returned": len(rows), "lines": [redact(r[0]) for r in rows]}

    def error_stats(self, start: str, end: str, group_by: str = "provider") -> dict[str, Any]:
        if group_by not in {"provider", "host", "error"}:
            return {"error": "group_by must be provider, host or error"}
        if group_by == "error":
            rows = self.con.execute(
                "SELECT COALESCE(error,'-') AS k, COUNT(*) AS n FROM events WHERE event='SUBMIT'"
                " AND status='FAILED' AND minute>=? AND minute<? GROUP BY k ORDER BY n DESC",
                (start, end),
            ).fetchall()
            return {"window": [start, end], "failed_by_error": {r["k"]: r["n"] for r in rows}}
        rows = self.con.execute(
            f"SELECT {group_by} AS k, COUNT(*) AS total,"
            " SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed"
            " FROM events WHERE event='SUBMIT' AND minute>=? AND minute<? GROUP BY k ORDER BY k",
            (start, end),
        ).fetchall()
        return {
            "window": [start, end],
            "groups": {
                r["k"]: {"submits": r["total"], "failed": r["failed"],
                         "fail_rate": round(r["failed"] / r["total"], 4) if r["total"] else None}
                for r in rows
            },
        }

    def trace_message(self, msgid: str) -> dict[str, Any]:
        rows = self.con.execute("SELECT raw FROM events WHERE msgid=? ORDER BY ts", (msgid,)).fetchall()
        return {"msgid": msgid, "lines": [redact(r[0]) for r in rows]}

    def slow_deliveries(self, start: str, end: str, provider: str | None = None, limit: int = 5) -> dict[str, Any]:
        params: list[Any] = [start, end]
        extra = ""
        if provider:
            extra = " AND s.provider = ?"
            params.append(provider)
        limit = max(1, min(int(limit), 20))
        rows = self.con.execute(
            f"""SELECT s.msgid, s.raw AS submit, d.raw AS dlr,
                       (julianday(d.ts) - julianday(s.ts)) * 86400.0 AS delay_s
                FROM events s JOIN events d ON d.msgid = s.msgid AND d.event = 'DLR'
                WHERE s.event = 'SUBMIT' AND s.minute >= ? AND s.minute < ?{extra}
                ORDER BY delay_s DESC LIMIT ?""",
            [*params, limit],
        ).fetchall()
        return {
            "window": [start, end],
            "messages": [
                {"msgid": r["msgid"], "delay_s": round(r["delay_s"], 1),
                 "submit": redact(r["submit"]), "dlr": redact(r["dlr"])}
                for r in rows
            ],
        }

    def compare_windows(self, a_start: str, a_end: str, b_start: str, b_end: str,
                        provider: str | None = None, host: str | None = None) -> dict[str, Any]:
        return {
            "A": self._window_metrics(a_start, a_end, provider, host),
            "B": self._window_metrics(b_start, b_end, provider, host),
            "scope": {"provider": provider, "host": host},
        }

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _filters(start: str | None, end: str | None, host: str | None = None,
                 provider: str | None = None) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        params: list[Any] = []
        if start:
            where.append("minute >= ?"); params.append(start)
        if end:
            where.append("minute < ?"); params.append(end)
        if host:
            where.append("host = ?"); params.append(host)
        if provider:
            where.append("provider = ?"); params.append(provider)
        return where, params

    def _window_metrics(self, start: str, end: str, provider: str | None, host: str | None) -> dict[str, Any]:
        where, params = self._filters(start, end, host=host, provider=provider)
        clause = " AND ".join(where)
        r = self.con.execute(
            f"""SELECT
                  COUNT(DISTINCT minute) AS minutes,
                  SUM(event='SUBMIT') AS submits,
                  SUM(event='SUBMIT' AND status='FAILED') AS failed,
                  SUM(event='RETRY') AS retries,
                  AVG(CASE WHEN event='SUBMIT' THEN latency_ms END) AS avg_latency_ms
                FROM events WHERE {clause}""",
            params,
        ).fetchone()
        # Queue depth is a per-host signal; it has no provider, so don't filter it by provider.
        q_where, q_params = self._filters(start, end, host=host)
        depth = self.con.execute(
            f"SELECT MAX(depth) FROM events WHERE event='QUEUE' AND {' AND '.join(q_where)}", q_params
        ).fetchone()[0]
        submits = r["submits"] or 0
        failed = r["failed"] or 0
        return {
            "window": [start, end],
            "submits": submits,
            "submits_per_min": round(submits / r["minutes"], 1) if r["minutes"] else 0,
            "failed": failed,
            "fail_rate": round(failed / submits, 4) if submits else None,
            "retries": r["retries"] or 0,
            "avg_latency_ms": round(r["avg_latency_ms"]) if r["avg_latency_ms"] is not None else None,
            "max_queue_depth": depth,
        }
