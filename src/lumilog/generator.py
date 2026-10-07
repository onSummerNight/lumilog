"""Synthetic SMS gateway log generator.

Produces realistic-looking but entirely fake logs, with optional injected
incidents so the detectors and the investigator have something to find.

Line format:
    2026-10-07 13:00:01.234 INFO  [gw-sms-01] SUBMIT msgid=... msisdn=... provider=... status=... latency_ms=...
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

PROVIDERS = {"TSEL": 0.5, "ISAT": 0.3, "XL": 0.2}
HOSTS = ["gw-sms-01", "gw-sms-02"]
PREFIXES = {"TSEL": ["62811", "62812", "62813"], "ISAT": ["62814", "62815", "62816"], "XL": ["62817", "62818", "62819"]}
SENDERS = ["DEMOBANK", "DEMOPAY", "OTP-SVC"]


@dataclass(frozen=True)
class Incident:
    kind: str
    start_min: int
    end_min: int
    target: str
    description: str


DEFAULT_INCIDENTS = (
    Incident("provider_timeout", 40, 55, "ISAT", "ISAT SMSC timeouts, most submits fail after retries"),
    Incident("queue_stall", 80, 95, "gw-sms-02", "gw-sms-02 stops submitting, outbound queue grows"),
    Incident("dlr_delay", 100, 110, "TSEL", "TSEL delivery reports arrive 5-15 minutes late"),
)


def _fmt(ts: datetime, level: str, host: str, event: str, **kv: object) -> str:
    fields = " ".join(f"{k}={v}" for k, v in kv.items())
    return f"{ts:%Y-%m-%d %H:%M:%S}.{ts.microsecond // 1000:03d} {level:<5} [{host}] {event} {fields}".rstrip()


def _active(incidents: tuple[Incident, ...], kind: str, minute: int, target: str) -> bool:
    return any(i.kind == kind and i.target == target and i.start_min <= minute < i.end_min for i in incidents)


def generate(
    start: datetime,
    minutes: int = 120,
    rate_per_min: int = 60,
    seed: int = 42,
    incidents: tuple[Incident, ...] = DEFAULT_INCIDENTS,
) -> list[str]:
    """Return log lines, sorted by timestamp."""
    rng = random.Random(seed)
    out: list[tuple[datetime, str]] = []
    queued: dict[str, int] = {h: 0 for h in HOSTS}
    seq = 0

    for minute in range(minutes):
        base = start + timedelta(minutes=minute)
        count = max(1, int(rng.gauss(rate_per_min, rate_per_min * 0.1)))

        for _ in range(count):
            seq += 1
            ts = base + timedelta(milliseconds=rng.randint(0, 59_999))
            host = rng.choice(HOSTS)
            provider = rng.choices(list(PROVIDERS), weights=list(PROVIDERS.values()))[0]
            msisdn = rng.choice(PREFIXES[provider]) + f"{rng.randint(0, 9_999_999):07d}"
            msgid = f"{seq:08x}"
            sender = rng.choice(SENDERS)

            if _active(incidents, "queue_stall", minute, host):
                queued[host] += 1
                continue

            if _active(incidents, "provider_timeout", minute, provider) and rng.random() < 0.7:
                for attempt in (1, 2):
                    out.append((ts + timedelta(seconds=10 * attempt),
                                _fmt(ts + timedelta(seconds=10 * attempt), "WARN", host, "RETRY",
                                     msgid=msgid, provider=provider, attempt=attempt + 1, reason="TIMEOUT")))
                fail_ts = ts + timedelta(seconds=30)
                out.append((fail_ts, _fmt(fail_ts, "ERROR", host, "SUBMIT", msgid=msgid, msisdn=msisdn,
                                          sender=sender, provider=provider, status="FAILED",
                                          error="TIMEOUT", latency_ms=30000)))
                continue

            if rng.random() < 0.005:
                out.append((ts, _fmt(ts, "ERROR", host, "SUBMIT", msgid=msgid, msisdn=msisdn, sender=sender,
                                     provider=provider, status="FAILED",
                                     error=rng.choice(["INVALID_NUMBER", "THROTTLED"]),
                                     latency_ms=rng.randint(50, 300))))
                continue

            out.append((ts, _fmt(ts, "INFO", host, "SUBMIT", msgid=msgid, msisdn=msisdn, sender=sender,
                                 provider=provider, status="ACCEPTED", latency_ms=rng.randint(80, 400))))

            if _active(incidents, "dlr_delay", minute, provider):
                delay = rng.uniform(300, 900)
            else:
                delay = rng.uniform(2, 30)
            dlr_ts = ts + timedelta(seconds=delay)
            r = rng.random()
            dlr_status = "DELIVERED" if r < 0.97 else ("UNDELIVERED" if r < 0.99 else "EXPIRED")
            out.append((dlr_ts, _fmt(dlr_ts, "INFO", host, "DLR", msgid=msgid, provider=provider,
                                     status=dlr_status)))

        for host in HOSTS:
            if not any(i.kind == "queue_stall" and i.target == host and i.start_min <= minute < i.end_min
                       for i in incidents):
                queued[host] = max(0, queued[host] - rng.randint(50, 200))
            depth = queued[host] + rng.randint(0, 5)
            q_ts = base + timedelta(seconds=59, milliseconds=999)
            out.append((q_ts, _fmt(q_ts, "INFO", host, "QUEUE", depth=depth)))

    out.sort(key=lambda x: x[0])
    return [line for _, line in out]
