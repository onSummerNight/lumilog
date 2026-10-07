"""Command line interface."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import typer

from . import detectors, generator, parser, store
from .report import ReportContext, build_offline_report
from .tools import Toolbox

app = typer.Typer(add_completion=False, help="LumiLog: incident analysis for SMS gateway logs.")


@app.command()
def generate(
    out: Path = typer.Option(Path("logs/sms-gateway.log"), help="Output log file."),
    start: str = typer.Option("2026-10-07 13:00", help="Start time, 'YYYY-MM-DD HH:MM'."),
    minutes: int = typer.Option(120, help="Duration in minutes."),
    rate: int = typer.Option(60, help="Average messages per minute."),
    seed: int = typer.Option(42, help="Random seed (same seed, same logs)."),
    clean: bool = typer.Option(False, "--clean", help="Generate without injected incidents."),
) -> None:
    """Generate synthetic SMS gateway logs."""
    lines = generator.generate(
        datetime.strptime(start, "%Y-%m-%d %H:%M"), minutes=minutes, rate_per_min=rate, seed=seed,
        incidents=() if clean else generator.DEFAULT_INCIDENTS,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.echo(f"Wrote {len(lines):,} lines to {out}")
    if not clean:
        typer.echo("Injected incidents:")
        for inc in generator.DEFAULT_INCIDENTS:
            typer.echo(f"  +{inc.start_min:>3}..{inc.end_min:<3} min  {inc.kind:<17} {inc.target:<10} {inc.description}")


@app.command()
def detect(
    path: Path = typer.Argument(..., help="Log file or directory of *.log files."),
    as_json: bool = typer.Option(False, "--json", help="Print findings as JSON."),
) -> None:
    """Parse logs and run deterministic detectors (no LLM)."""
    result = parser.parse_path(path)
    con = store.connect()
    store.load(con, result.events)
    findings = detectors.run_all(con)

    if as_json:
        typer.echo(json.dumps([f.to_dict() for f in findings], indent=2))
        return

    first, last = store.time_range(con)
    typer.echo(f"Parsed {len(result.events):,} events ({len(result.unparsed)} unparsed), {first} .. {last}")
    if not findings:
        typer.echo("No incidents detected.")
        return
    typer.echo(f"\n{len(findings)} finding(s):\n")
    for f in findings:
        typer.echo(f"[{f.severity.upper():<8}] {f.start} -> {f.end}  {f.kind:<22} {f.scope}")
        typer.echo(f"            {f.summary}")


@app.command()
def analyze(
    path: Path = typer.Argument(..., help="Log file or directory of *.log files."),
    out: Path = typer.Option(Path("incident-report.md"), help="Where to write the Markdown report."),
    offline: bool = typer.Option(False, "--offline", help="Rule-based report, no API calls."),
    model: str = typer.Option("", help="Claude model id (default: investigator.DEFAULT_MODEL)."),
    max_turns: int = typer.Option(15, help="Maximum agent turns in Claude mode."),
) -> None:
    """Detect incidents and write an incident report (Claude, or --offline)."""
    result = parser.parse_path(path)
    con = store.connect()
    store.load(con, result.events)
    findings = detectors.run_all(con)
    first, last = store.time_range(con)
    ctx = ReportContext(source=str(path), first_ts=first, last_ts=last,
                        events=len(result.events), unparsed=len(result.unparsed))
    tb = Toolbox(con)

    use_claude = not offline
    if use_claude and not os.environ.get("ANTHROPIC_API_KEY"):
        typer.echo("ANTHROPIC_API_KEY is not set, using --offline mode.")
        use_claude = False

    if not use_claude:
        report = build_offline_report(findings, tb, ctx)
    else:
        from .investigator import DEFAULT_MODEL, ClaudeInvestigator, anthropic_client

        inv = ClaudeInvestigator(anthropic_client(), tb, model=model or DEFAULT_MODEL, max_turns=max_turns)
        res = inv.investigate(findings, ctx)
        report = res.report
        typer.echo(f"Claude: {res.turns} turns, {len(res.tool_calls)} tool calls, "
                   f"{res.input_tokens:,} in / {res.output_tokens:,} out tokens"
                   + (" (stopped at turn limit)" if res.stopped_early else ""))

    out.write_text(report + "\n", encoding="utf-8")
    typer.echo(f"{len(findings)} finding(s). Report written to {out}")


if __name__ == "__main__":
    app()
