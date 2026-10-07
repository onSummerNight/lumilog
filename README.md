# LumiLog

[![tests](https://github.com/onSummerNight/lumilog/actions/workflows/tests.yml/badge.svg)](https://github.com/onSummerNight/lumilog/actions/workflows/tests.yml)

Incident analysis for SMS gateway logs.

LumiLog parses gateway logs, finds incidents with deterministic detectors, and investigates them: it compares each incident against a normal period, checks which providers and hosts were affected, collects evidence lines, and writes a Markdown incident report with likely causes and next checks.

The split is deliberate: **numbers come from code that can be tested; the investigator only reasons over facts it can query.**

```
log files ─► parser ─► SQLite store ─► detectors ─► findings
                            │                          │
                            └──── tools (redacted) ◄───┤
                                                       ▼
                                 investigator: offline rules  or  Claude agent
                                                       │
                                               incident-report.md
```

## What you get

From two hours of gateway logs, a report like this for each incident (excerpt from the [full example](examples/incident-report-offline.md)):

> **1. Submit failures at provider ISAT** · 13:41 → 13:56 (15 min) · critical
>
> | Metric | Incident 13:41–13:56 | Normal 13:24–13:39 |
> |---|---|---|
> | Failed submits | 166 | 2 |
> | Failure rate | 63.8% | 0.8% |
> | Retries | 331 | 0 |
> | Avg submit latency (ms) | 19,238 | 241 |
>
> **Likely cause** (confidence: high): Problem on the ISAT side. Failures are concentrated on ISAT (dominant error: TIMEOUT) while other providers stayed normal in the same window (TSEL 0.0%, XL 0.0%), so the gateways themselves were healthy.

## Quick start

```bash
pip install -e ".[dev]"

lumilog generate                                 # 2h of synthetic logs, 3 injected incidents
lumilog detect  logs/sms-gateway.log             # list findings
lumilog analyze logs/sms-gateway.log --offline   # full report, no API key needed
pytest
```

### Claude mode

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...
lumilog analyze logs/sms-gateway.log
```

Claude receives the findings and investigates with the same tools, then writes the report. Without an API key, `analyze` falls back to offline mode automatically.

## Investigator tools

Both investigators use these; the Claude agent calls them through tool use.

| Tool | Returns |
|---|---|
| `search_logs` | Matching raw lines (redacted) by time, host, provider, level, event, substring |
| `error_stats` | Submits, failures and failure rate grouped by provider, host or error |
| `trace_message` | Every line for one message id |
| `slow_deliveries` | Messages with the longest submit-to-delivery-report delay, with both lines |
| `compare_windows` | Key metrics for an incident window vs a normal window |

## Detectors

| Detector | Signal |
|---|---|
| `provider_failure_spike` | Per-provider submit failure rate far above its own baseline (minimum volume and failure count to avoid noise) |
| `queue_stall` | Host queue depth high while that host's submit rate collapses |
| `dlr_delay` | Per-provider p90 time from submit to delivery report above threshold |

Baselines for comparison are chosen automatically: same length as the incident, inside the data, and clear of every incident window with a safety gap.

## Log format

All data in this repository is synthetic. One event per line:

```
2026-10-07 13:00:01.234 INFO  [gw-sms-01] SUBMIT msgid=0000002a msisdn=628121234567 sender=DEMOBANK provider=TSEL status=ACCEPTED latency_ms=210
2026-10-07 13:00:14.901 INFO  [gw-sms-01] DLR msgid=0000002a provider=TSEL status=DELIVERED
2026-10-07 13:40:12.004 WARN  [gw-sms-02] RETRY msgid=00000b1c provider=ISAT attempt=2 reason=TIMEOUT
2026-10-07 13:00:59.999 INFO  [gw-sms-02] QUEUE depth=3
```

Unknown `key=value` fields are kept, and lines that don't parse are counted rather than dropped silently.

## Privacy

Everything a tool returns passes through `lumilog.redact`, which masks phone numbers, IPv4 addresses and email addresses. Message ids are kept for tracing. Only redacted tool output and detector findings are ever sent to the model.

## Roadmap

- [x] Synthetic generator, parser, store, detectors, redaction
- [x] Investigator tools and offline report
- [x] Claude agent loop (tool use, turn budget, token accounting), tested with a scripted client
- [ ] Run Claude mode against the synthetic incidents and publish an example report
- [ ] WhatsApp Business API log format
- [ ] Small web UI

## License

MIT

---

A [LumiDev](https://lumidev.online) project, built by Luminous together with Claude.
