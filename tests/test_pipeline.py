from datetime import datetime

import pytest

from lumilog import detectors, generator, parser, store
from lumilog.redact import redact

START = datetime(2026, 10, 7, 13, 0)


@pytest.fixture(scope="module")
def incident_db():
    lines = generator.generate(START, minutes=120, rate_per_min=60, seed=42)
    res = parser.parse_lines(lines)
    assert not res.unparsed
    con = store.connect()
    store.load(con, res.events)
    return con


def _minute(offset: int) -> str:
    return f"2026-10-07 {13 + offset // 60:02d}:{offset % 60:02d}"


def test_generator_is_deterministic():
    a = generator.generate(START, minutes=5, seed=7)
    b = generator.generate(START, minutes=5, seed=7)
    assert a == b


def test_parse_line_fields():
    ev = parser.parse_line(
        "2026-10-07 13:00:01.234 ERROR [gw-sms-01] SUBMIT msgid=0000002a msisdn=628141234567 "
        "provider=ISAT status=FAILED error=TIMEOUT latency_ms=30000 custom=x"
    )
    assert ev and ev.level == "ERROR" and ev.host == "gw-sms-01"
    assert ev.provider == "ISAT" and ev.error == "TIMEOUT" and ev.latency_ms == 30000
    assert ev.extra == {"custom": "x"}


def test_unparsed_lines_are_reported():
    res = parser.parse_lines(["garbage", "2026-10-07 13:00:00.000 INFO  [h] QUEUE depth=1"])
    assert len(res.events) == 1 and res.unparsed == [(1, "garbage")]


def test_detects_all_injected_incidents(incident_db):
    found = {(f.kind, f.scope): f for f in detectors.run_all(incident_db)}
    expected = {
        ("provider_failure_spike", "ISAT"): (40, 55),
        ("queue_stall", "gw-sms-02"): (80, 95),
        ("dlr_delay", "TSEL"): (100, 110),
    }
    for key, (s, e) in expected.items():
        assert key in found, f"missing {key}; got {list(found)}"
        f = found[key]
        assert abs(_to_off(f.start) - s) <= 1 and abs(_to_off(f.end) - e) <= 1, (key, f.start, f.end)


def test_clean_logs_have_no_findings():
    lines = generator.generate(START, minutes=60, seed=3, incidents=())
    con = store.connect()
    store.load(con, parser.parse_lines(lines).events)
    assert detectors.run_all(con) == []


def _to_off(minute: str) -> int:
    hh, mm = minute[-5:].split(":")
    return (int(hh) - 13) * 60 + int(mm)


@pytest.mark.parametrize("raw,expected", [
    ("msisdn=628141234567", "msisdn=62814****567"),
    ("call 081234567890 now", "call 08123****890 now"),
    ("host 10.20.30.40 down", "host <ip> down"),
    ("mail ops@example.com", "mail <email>"),
    ("msgid=0000002a", "msgid=0000002a"),
])
def test_redaction(raw, expected):
    assert redact(raw) == expected
