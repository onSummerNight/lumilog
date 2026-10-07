"""Deterministic incident detectors.

Each detector works on per-minute aggregates from the event store and
returns Findings: time windows where something measurably went wrong.
These are facts the investigator (LLM) reasons over; it never computes them.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

MIN_FMT = "%Y-%m-%d %H:%M"


@dataclass
class Finding:
    kind: str
    scope: str
    start: str
    end: str
    severity: str
    summary: str
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _merge_minutes(minutes: list[str], gap: int = 1) -> list[tuple[str, str]]:
    """Merge sorted minute strings into [start, end) windows, allowing small gaps."""
    if not minutes:
        return []
    ts = sorted(datetime.strptime(m, MIN_FMT) for m in minutes)
    windows: list[tuple[datetime, datetime]] = []
    start = prev = ts[0]
    for t in ts[1:]:
        if t - prev > timedelta(minutes=gap + 1):
            windows.append((start, prev))
            start = t
        prev = t
    windows.append((start, prev))
    return [(s.strftime(MIN_FMT), (e + timedelta(minutes=1)).strftime(MIN_FMT)) for s, e in windows]


def _in_window(minute: str, start: str, end: str) -> bool:
    return start <= minute < end


def provider_failure_spikes(con: sqlite3.Connection, min_volume: int = 10, min_failed: int = 3,
                            min_rate: float = 0.15, factor: float = 5.0) -> list[Finding]:
    rows = con.execute(
        """SELECT minute, provider, COUNT(*) AS total,
                  SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed
           FROM events WHERE event = 'SUBMIT' AND provider IS NOT NULL
           GROUP BY minute, provider"""
    ).fetchall()
    by_provider: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_provider[r["provider"]].append(r)

    findings: list[Finding] = []
    for provider, prow in sorted(by_provider.items()):
        rates = [r["failed"] / r["total"] for r in prow if r["total"] >= min_volume]
        if not rates:
            continue
        baseline = statistics.median(rates)
        threshold = max(min_rate, baseline * factor)
        flagged = [
            r["minute"] for r in prow
            if r["total"] >= min_volume and r["failed"] >= min_failed and r["failed"] / r["total"] >= threshold
        ]
        for start, end in _merge_minutes(flagged):
            win = [r for r in prow if _in_window(r["minute"], start, end)]
            total = sum(r["total"] for r in win)
            failed = sum(r["failed"] for r in win)
            peak = max(r["failed"] / r["total"] for r in win if r["total"])
            errors = dict(con.execute(
                "SELECT error, COUNT(*) FROM events WHERE event='SUBMIT' AND status='FAILED'"
                " AND provider=? AND minute>=? AND minute<? GROUP BY error ORDER BY 2 DESC",
                (provider, start, end)).fetchall())
            severity = "critical" if peak >= 0.5 else "major" if peak >= 0.2 else "minor"
            findings.append(Finding(
                kind="provider_failure_spike", scope=provider, start=start, end=end, severity=severity,
                summary=f"{provider} submit failures {failed}/{total} ({failed / total:.0%}), "
                        f"peak {peak:.0%}/min vs baseline {baseline:.1%}",
                metrics={"submits": total, "failed": failed, "peak_rate": round(peak, 3),
                         "baseline_rate": round(baseline, 4), "errors": errors},
            ))
    return findings


def queue_stalls(con: sqlite3.Connection, min_depth: int = 50, low_ratio: float = 0.1) -> list[Finding]:
    depth_rows = con.execute(
        "SELECT minute, host, MAX(depth) AS depth FROM events WHERE event='QUEUE' GROUP BY minute, host"
    ).fetchall()
    submit_rows = con.execute(
        "SELECT minute, host, COUNT(*) AS n FROM events WHERE event='SUBMIT' GROUP BY minute, host"
    ).fetchall()
    submits = {(r["minute"], r["host"]): r["n"] for r in submit_rows}

    by_host: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in depth_rows:
        by_host[r["host"]].append((r["minute"], r["depth"] or 0))

    findings: list[Finding] = []
    for host, series in sorted(by_host.items()):
        series.sort()
        host_submits = [submits.get((m, host), 0) for m, _ in series]
        median_submits = statistics.median(host_submits) if host_submits else 0
        flagged = [
            m for (m, d), n in zip(series, host_submits)
            if d >= min_depth and n <= median_submits * low_ratio
        ]
        for start, end in _merge_minutes(flagged):
            win = [(m, d) for m, d in series if _in_window(m, start, end)]
            peak = max(d for _, d in win)
            sent = sum(submits.get((m, host), 0) for m, _ in win)
            findings.append(Finding(
                kind="queue_stall", scope=host, start=start, end=end,
                severity="critical" if peak >= 500 else "major",
                summary=f"{host} queue grew to {peak} while it submitted {sent} messages "
                        f"(normal ~{median_submits:.0f}/min)",
                metrics={"peak_depth": peak, "submits_in_window": sent,
                         "normal_submits_per_min": median_submits},
            ))
    return findings


def dlr_delays(con: sqlite3.Connection, threshold_s: float = 120.0, min_count: int = 5) -> list[Finding]:
    rows = con.execute(
        """SELECT s.minute AS minute, s.provider AS provider,
                  (julianday(d.ts) - julianday(s.ts)) * 86400.0 AS delay
           FROM events s JOIN events d ON d.msgid = s.msgid AND d.event = 'DLR'
           WHERE s.event = 'SUBMIT' AND s.status = 'ACCEPTED'"""
    ).fetchall()
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        buckets[(r["provider"], r["minute"])].append(r["delay"])

    def p90(xs: list[float]) -> float:
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]

    by_provider: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for (prov, minute), delays in buckets.items():
        if len(delays) >= min_count:
            by_provider[prov].append((minute, p90(delays), len(delays)))

    findings: list[Finding] = []
    for provider, series in sorted(by_provider.items()):
        baseline = statistics.median(p for _, p, _ in series)
        flagged = [m for m, p, _ in series if p >= threshold_s]
        for start, end in _merge_minutes(flagged):
            win = [(m, p, n) for m, p, n in series if _in_window(m, start, end)]
            peak = max(p for _, p, _ in win)
            findings.append(Finding(
                kind="dlr_delay", scope=provider, start=start, end=end,
                severity="major" if peak >= 600 else "minor",
                summary=f"{provider} delivery reports delayed: p90 up to {peak / 60:.1f} min "
                        f"(normal p90 ~{baseline:.0f}s)",
                metrics={"peak_p90_s": round(peak, 1), "baseline_p90_s": round(baseline, 1),
                         "messages": sum(n for _, _, n in win)},
            ))
    return findings


def run_all(con: sqlite3.Connection) -> list[Finding]:
    findings = provider_failure_spikes(con) + queue_stalls(con) + dlr_delays(con)
    return sorted(findings, key=lambda f: (f.start, f.kind))
