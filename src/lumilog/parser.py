"""Parse SMS gateway log lines into normalized events."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(?P<level>[A-Z]+)\s+\[(?P<host>[^\]]+)\]\s+(?P<event>[A-Z_]+)\s*(?P<rest>.*)$"
)
KV_RE = re.compile(r"(\w+)=(\S+)")
INT_FIELDS = {"latency_ms", "depth", "attempt"}


@dataclass
class Event:
    ts: datetime
    level: str
    host: str
    event: str
    msgid: str | None = None
    msisdn: str | None = None
    provider: str | None = None
    status: str | None = None
    error: str | None = None
    latency_ms: int | None = None
    depth: int | None = None
    attempt: int | None = None
    raw: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    events: list[Event]
    unparsed: list[tuple[int, str]]


KNOWN = {"msgid", "msisdn", "provider", "status", "error", "latency_ms", "depth", "attempt"}


def parse_line(line: str) -> Event | None:
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    ev = Event(
        ts=datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S.%f"),
        level=m["level"],
        host=m["host"],
        event=m["event"],
        raw=line.rstrip("\n"),
    )
    for k, v in KV_RE.findall(m["rest"]):
        if k in KNOWN:
            setattr(ev, k, int(v) if k in INT_FIELDS and v.lstrip("-").isdigit() else v)
        else:
            ev.extra[k] = v
    return ev


def parse_lines(lines: Iterable[str]) -> ParseResult:
    events: list[Event] = []
    unparsed: list[tuple[int, str]] = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        ev = parse_line(line)
        if ev is None:
            unparsed.append((n, line.rstrip("\n")))
        else:
            events.append(ev)
    return ParseResult(events, unparsed)


def iter_files(path: Path) -> Iterator[str]:
    files = sorted(path.glob("*.log")) if path.is_dir() else [path]
    for f in files:
        with f.open(encoding="utf-8", errors="replace") as fh:
            yield from fh


def parse_path(path: Path) -> ParseResult:
    return parse_lines(iter_files(path))
