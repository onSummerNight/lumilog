# Context: LumiLog

Status: LOCKED 2026-10-07

## Problem

When an SMS gateway misbehaves, an engineer greps logs by hand to work out what failed, where, and since when.

## Users

Engineers who operate SMS and messaging gateways: NOC teams, gateway operators, integrators.

## Scope v1

- Parse gateway logs into normalised events (one documented line format first)
- Detect incidents deterministically: provider failure spikes, queue stalls, delivery-report delays
- Investigate each finding with query tools and write a Markdown incident report
- Two investigators: offline rules (no API key) and a Claude agent using the same tools
- Redact phone numbers, IPs and emails before anything leaves the machine

## Non-goals

- Real-time monitoring or alerting
- A web UI (later)
- Real logs in this repository: synthetic data only

## Success check

`pytest` passes, and `lumilog analyze` on generated logs reports exactly the injected incidents with correct windows.

## Stack

Python 3.10+, standard library plus Typer. Optional `anthropic` package for Claude mode.

## Constraints

Clean room. Every number in a report comes from code, never from the model.

## Open questions

- Second log format: WhatsApp Business API events
- Publishing a Claude-mode example report (needs API credit)
