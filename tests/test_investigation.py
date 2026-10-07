import copy
import json
import re
from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from lumilog import detectors, generator, parser, store
from lumilog.investigator import ClaudeInvestigator
from lumilog.report import ReportContext, build_offline_report
from lumilog.tools import TOOL_SPECS, Toolbox


@pytest.fixture(scope="module")
def env():
    lines = generator.generate(datetime(2026, 10, 7, 13, 0), minutes=120, seed=42)
    res = parser.parse_lines(lines)
    con = store.connect()
    store.load(con, res.events)
    first, last = store.time_range(con)
    ctx = ReportContext("synthetic.log", first, last, len(res.events), 0)
    return con, Toolbox(con), detectors.run_all(con), ctx


# -- tools ---------------------------------------------------------------

def test_tool_specs_match_toolbox(env):
    _, tb, _, _ = env
    for spec in TOOL_SPECS:
        assert hasattr(tb, spec["name"])
        assert spec["input_schema"]["type"] == "object"


def test_search_logs_is_redacted_and_limited(env):
    _, tb, _, _ = env
    out = tb.search_logs(event="SUBMIT", limit=500)
    assert out["returned"] == 50 and out["total_matches"] > 50
    assert all("msisdn=628" in l and "*" in l for l in out["lines"])


def test_error_stats_and_compare(env):
    _, tb, _, _ = env
    s = tb.error_stats("2026-10-07 13:41", "2026-10-07 13:56", "provider")["groups"]
    assert s["ISAT"]["fail_rate"] > 0.5 and s["TSEL"]["fail_rate"] < 0.05
    c = tb.compare_windows("2026-10-07 13:41", "2026-10-07 13:56", "2026-10-07 13:25", "2026-10-07 13:40",
                           provider="ISAT")
    assert c["A"]["retries"] > 100 and c["B"]["retries"] == 0


def test_trace_message_and_errors(env):
    _, tb, _, _ = env
    msgid = tb.search_logs(event="DLR", limit=1)["lines"][0].split("msgid=")[1].split()[0]
    lines = tb.trace_message(msgid)["lines"]
    assert [("SUBMIT" in l, "DLR" in l) for l in lines] == [(True, False), (False, True)]
    assert "error" in json.loads(tb.call("nope", {}))
    assert "error" in json.loads(tb.call("error_stats", {"bad": 1}))


# -- offline report ------------------------------------------------------

def test_slow_deliveries_show_delay(env):
    _, tb, _, _ = env
    msgs = tb.slow_deliveries("2026-10-07 14:40", "2026-10-07 14:50", provider="TSEL", limit=3)["messages"]
    assert len(msgs) == 3 and all(m["delay_s"] > 300 for m in msgs)
    assert all("SUBMIT" in m["submit"] and "DLR" in m["dlr"] for m in msgs)


def test_baselines_avoid_every_incident(env):
    from lumilog.report import baseline_window
    _, _, findings, ctx = env
    for f in findings:
        s, e = baseline_window(f, findings, ctx.first_ts[:16], "2026-10-07 15:05")
        for x in findings:
            assert e <= x.start or s >= x.end, (f.kind, s, e, x.kind)


def test_offline_report_covers_every_incident(env):
    _, tb, findings, ctx = env
    md = build_offline_report(findings, tb, ctx)
    for title in ("Submit failures at provider ISAT", "Queue stall on gw-sms-02",
                  "Delayed delivery reports from TSEL"):
        assert title in md
    assert "confidence: high" in md          # ISAT: other providers were healthy
    assert not re.search(r"628\d{8,}", md)    # no unmasked phone numbers
    assert "```" in md and "Next checks" in md


# -- Claude loop with a scripted fake client -----------------------------

def _tool(i, name, inp):
    return NS(type="tool_use", id=f"tu_{i}", name=name, input=inp)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        content = self.script.pop(0)
        return NS(content=content, usage=NS(input_tokens=100, output_tokens=20),
                  stop_reason="tool_use" if any(b.type == "tool_use" for b in content) else "end_turn")


def _assert_valid_conversation(messages):
    assert messages[0]["role"] == "user"
    for a, b in zip(messages, messages[1:]):
        assert a["role"] != b["role"], "roles must alternate"
    for i, m in enumerate(messages):
        if m["role"] == "assistant":
            ids = [b["id"] for b in m["content"] if b["type"] == "tool_use"]
            if ids:
                nxt = messages[i + 1]["content"]
                assert [b["tool_use_id"] for b in nxt if b["type"] == "tool_result"] == ids


def test_claude_loop_runs_tools_and_returns_report(env):
    _, tb, findings, ctx = env
    client = FakeClient([
        [NS(type="text", text="Checking ISAT."),
         _tool(1, "compare_windows", {"a_start": "2026-10-07 13:41", "a_end": "2026-10-07 13:56",
                                      "b_start": "2026-10-07 13:26", "b_end": "2026-10-07 13:41",
                                      "provider": "ISAT"}),
         _tool(2, "error_stats", {"start": "2026-10-07 13:41", "end": "2026-10-07 13:56"})],
        [_tool(3, "search_logs", {"provider": "ISAT", "level": "ERROR", "limit": 3})],
        [NS(type="text", text="# Incident report\n## Summary\n1. ISAT timeouts")],
    ])
    res = ClaudeInvestigator(client, tb).investigate(findings, ctx)

    assert res.report.startswith("# Incident report")
    assert [c["name"] for c in res.tool_calls] == ["compare_windows", "error_stats", "search_logs"]
    assert res.turns == 3 and res.input_tokens == 300 and not res.stopped_early
    assert all(c["tools"] == TOOL_SPECS for c in client.calls)
    final_msgs = client.calls[-1]["messages"]
    _assert_valid_conversation(final_msgs)
    assert "provider_failure_spike" in final_msgs[0]["content"]
    tool_result = json.loads(final_msgs[2]["content"][0]["content"])
    assert tool_result["A"]["retries"] > 100


def test_claude_loop_turn_limit(env):
    _, tb, findings, ctx = env
    loop = [[_tool(i, "error_stats", {"start": "2026-10-07 13:00", "end": "2026-10-07 14:00"})] for i in range(2)]
    client = FakeClient(loop + [[NS(type="text", text="# Incident report\npartial")]])
    res = ClaudeInvestigator(client, tb, max_turns=2).investigate(findings, ctx)

    assert res.stopped_early and res.report.endswith("partial")
    last = client.calls[-1]
    assert last["tool_choice"] == {"type": "none"}
    _assert_valid_conversation(last["messages"])
    assert last["messages"][-1]["content"][-1]["type"] == "text"
