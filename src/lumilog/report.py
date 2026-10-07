"""Offline (rule-based) investigator.

Produces a complete Markdown incident report from detector findings and the
same tools the LLM investigator uses. No network, no API key, no cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .detectors import MIN_FMT, Finding
from .tools import Toolbox

TITLES = {
    "provider_failure_spike": "Submit failures at provider {scope}",
    "queue_stall": "Queue stall on {scope}",
    "dlr_delay": "Delayed delivery reports from {scope}",
}


@dataclass
class ReportContext:
    source: str
    first_ts: str | None
    last_ts: str | None
    events: int
    unparsed: int


def _dt(minute: str) -> datetime:
    return datetime.strptime(minute, MIN_FMT)


def _shift(minute: str, delta_min: int) -> str:
    return (_dt(minute) + timedelta(minutes=delta_min)).strftime(MIN_FMT)


def _length(f: Finding) -> int:
    return int((_dt(f.end) - _dt(f.start)).total_seconds() // 60)


def baseline_window(f: Finding, findings: list[Finding], data_start: str, data_end: str,
                    gap: int = 2) -> tuple[str, str]:
    """A same-length 'normal' window that overlaps no incident (with a safety gap) and lies inside the data.

    Detector windows can start a minute late (the first minute may be below threshold),
    so a gap keeps the incident's ramp-up out of the baseline.
    """
    n = _length(f)
    busy = [(_shift(x.start, -gap), _shift(x.end, gap)) for x in findings]

    def free(s: str, e: str) -> bool:
        return s >= data_start and e <= data_end and all(e <= bs or s >= be for bs, be in busy)

    candidates = [(_shift(f.start, -gap - n), _shift(f.start, -gap)),
                  (_shift(f.end, gap), _shift(f.end, gap + n))]
    candidates += [(_shift(f.start, -gap - n * k), _shift(f.start, -gap - n * (k - 1))) for k in range(2, 8)]
    for s, e in candidates:
        if free(s, e):
            return s, e
    return candidates[0]


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _fmt(v: object) -> str:
    return "n/a" if v is None else f"{v:,}" if isinstance(v, int) else str(v)


def _evidence_table(cmp: dict) -> list[str]:
    a, b = cmp["A"], cmp["B"]
    rows = [
        ("Submits / min", a["submits_per_min"], b["submits_per_min"]),
        ("Failed submits", _fmt(a["failed"]), _fmt(b["failed"])),
        ("Failure rate", _pct(a["fail_rate"]), _pct(b["fail_rate"])),
        ("Retries", _fmt(a["retries"]), _fmt(b["retries"])),
        ("Avg submit latency (ms)", _fmt(a["avg_latency_ms"]), _fmt(b["avg_latency_ms"])),
        ("Max queue depth", _fmt(a["max_queue_depth"]), _fmt(b["max_queue_depth"])),
    ]
    out = [f"| Metric | Incident {a['window'][0][-5:]}–{a['window'][1][-5:]} "
           f"| Normal {b['window'][0][-5:]}–{b['window'][1][-5:]} |",
           "|---|---|---|"]
    out += [f"| {m} | {x} | {y} |" for m, x, y in rows]
    return out


def _provider_failures(f: Finding, tb: Toolbox) -> str:
    groups = tb.error_stats(f.start, f.end, "provider")["groups"]
    return ", ".join(f"{p} {_pct(g['fail_rate'])}" for p, g in sorted(groups.items())) or "no submits"


def _section_provider(f: Finding, tb: Toolbox) -> dict:
    groups = tb.error_stats(f.start, f.end, "provider")["groups"]
    others = {p: g for p, g in groups.items() if p != f.scope}
    others_ok = all((g["fail_rate"] or 0) < 0.05 for g in others.values())
    other_txt = ", ".join(f"{p} {_pct(g['fail_rate'])}" for p, g in sorted(others.items()))
    top_error = next(iter(f.metrics.get("errors", {})), "unknown")
    if others_ok:
        cause = (f"Problem on the {f.scope} side. Failures are concentrated on {f.scope} "
                 f"(dominant error: {top_error}) while other providers stayed normal in the same window "
                 f"({other_txt}), so the gateways themselves were healthy.")
        conf = "high"
    else:
        cause = (f"Failures on {f.scope} (dominant error: {top_error}) coincided with elevated failures on other "
                 f"providers ({other_txt}). A shared cause on the gateway or network side is more likely.")
        conf = "medium"
    sample = tb.search_logs(start=f.start, end=f.end, provider=f.scope, level="ERROR", limit=4)
    return {
        "cause": cause, "confidence": conf,
        "evidence_title": f"Sample failed submits ({sample['returned']} of {sample['total_matches']:,})",
        "evidence": sample["lines"],
        "checks": [
            f"Confirm with {f.scope} whether their SMSC had an outage or throttling in this window.",
            f"Check network path and bind/session status from the gateways to {f.scope}.",
            "Decide whether failed messages need resending; OTP messages are usually stale after a few minutes.",
            f"Consider automatic failover to another route when {f.scope} timeouts exceed a threshold.",
        ],
    }


def _section_queue(f: Finding, tb: Toolbox) -> dict:
    hosts = tb.error_stats(f.start, f.end, "host")["groups"]
    other_txt = ", ".join(f"{h} sent {g['submits']}" for h, g in sorted(hosts.items()) if h != f.scope) \
        or "no other host sent anything"
    prov_txt = _provider_failures(f, tb)
    sample = tb.search_logs(start=f.start, end=f.end, host=f.scope, event="QUEUE", limit=5)
    return {
        "cause": (f"{f.scope} stopped sending while its outbound queue kept growing. Other hosts kept working "
                  f"({other_txt}) and provider failure rates in the same window were normal ({prov_txt}), "
                  f"which points to {f.scope} itself: a hung sender process, lost provider binds, "
                  "or an exhausted connection pool. The logs show the symptom, not which of these it was."),
        "confidence": "medium",
        "evidence_title": f"Queue depth on {f.scope} (first {sample['returned']} minutes)",
        "evidence": sample["lines"],
        "checks": [
            f"Check the sender process on {f.scope} (alive, stuck threads, restarts) around {f.start[-5:]}.",
            f"Check provider bind/session status on {f.scope} at the stall start.",
            "Verify the backlog drained after recovery and no messages were dropped.",
            "Add an alert on queue depth rising while submit rate is near zero.",
        ],
    }


def _section_dlr(f: Finding, tb: Toolbox, cmp: dict) -> dict:
    slow = tb.slow_deliveries(f.start, f.end, provider=f.scope, limit=3)["messages"]
    evidence: list[str] = []
    for m in slow:
        evidence += [f"# msgid {m['msgid']}: report after {m['delay_s'] / 60:.1f} min", m["submit"], m["dlr"]]
    return {
        "cause": (f"Messages to {f.scope} were accepted normally (submit failure rate {_pct(cmp['A']['fail_rate'])}, "
                  f"avg latency {_fmt(cmp['A']['avg_latency_ms'])} ms vs {_fmt(cmp['B']['avg_latency_ms'])} ms normally) "
                  f"but delivery reports came back late (p90 up to {f.metrics['peak_p90_s'] / 60:.1f} min vs "
                  f"~{f.metrics['baseline_p90_s']:.0f}s normally). The delay is on the {f.scope} delivery-report "
                  "path, not in sending."),
        "confidence": "medium",
        "evidence_title": "Slowest deliveries (submit and report)",
        "evidence": evidence,
        "checks": [
            f"Ask {f.scope} whether their delivery-report pipeline was delayed in this window.",
            "Confirm whether end users actually received messages late, or only the reports were late.",
            "Check that delayed reports did not trigger unnecessary resends or timeouts in upstream apps.",
        ],
    }


def build_offline_report(findings: list[Finding], tb: Toolbox, ctx: ReportContext) -> str:
    data_start = (ctx.first_ts or "")[:16]
    data_end = _shift((ctx.last_ts or data_start)[:16], 1) if ctx.last_ts else data_start
    lines = [
        "# Incident report",
        "",
        f"- **Source:** `{ctx.source}`",
        f"- **Period:** {ctx.first_ts} → {ctx.last_ts}",
        f"- **Events:** {ctx.events:,} parsed, {ctx.unparsed} unparsed",
        "- **Mode:** offline (rule-based). Every number comes from the log data.",
        "",
        "## Summary",
        "",
    ]
    if not findings:
        return "\n".join(lines + ["No incidents detected in this period.", ""])

    order = {"critical": 0, "major": 1, "minor": 2}
    for i, f in enumerate(sorted(findings, key=lambda x: (order.get(x.severity, 9), x.start)), 1):
        lines.append(f"{i}. **{f.severity.upper()}** {f.start[-5:]}–{f.end[-5:]} · "
                     f"{TITLES[f.kind].format(scope=f.scope)}: {f.summary}")
    lines += ["", "## Timeline", "", "| Start | End | Severity | Incident |", "|---|---|---|---|"]
    lines += [f"| {f.start} | {f.end} | {f.severity} | {TITLES[f.kind].format(scope=f.scope)} |" for f in findings]
    lines.append("")

    for i, f in enumerate(findings, 1):
        base = baseline_window(f, findings, data_start, data_end)
        scope = {"host": f.scope} if f.kind == "queue_stall" else {"provider": f.scope}
        cmp = tb.compare_windows(f.start, f.end, *base, **scope)
        if f.kind == "provider_failure_spike":
            sec = _section_provider(f, tb)
        elif f.kind == "queue_stall":
            sec = _section_queue(f, tb)
        else:
            sec = _section_dlr(f, tb, cmp)

        lines += [
            f"## {i}. {TITLES[f.kind].format(scope=f.scope)}",
            "",
            f"**Window:** {f.start} → {f.end} ({_length(f)} min) · **Severity:** {f.severity}",
            "",
            f"**What happened:** {f.summary}.",
            "",
            *_evidence_table(cmp),
            "",
            f"**{sec['evidence_title']}:**",
            "",
            "```",
            *sec["evidence"],
            "```",
            "",
            f"**Likely cause** (confidence: {sec['confidence']}): {sec['cause']}",
            "",
            "**Next checks:**",
            "",
            *[f"- {c}" for c in sec["checks"]],
            "",
        ]
    return "\n".join(lines)
