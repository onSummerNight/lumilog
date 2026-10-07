"""Claude investigator: an agent loop with tool use.

The model receives the deterministic findings, investigates with the tools
in lumilog.tools, and writes a Markdown incident report. The client is
injected, so the loop can be tested without network access or an API key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from .detectors import Finding
from .report import ReportContext
from .tools import TOOL_SPECS, Toolbox

DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """You are an experienced NOC engineer investigating incidents in SMS gateway logs.

You receive incident findings produced by deterministic detectors. They are reliable facts.
Use the tools to gather evidence, confirm scope, and narrow down causes. Then write the report.

Rules:
- Every number in the report must come from the findings or from a tool result. Never estimate or invent numbers.
- Quote evidence as log lines exactly as the tools return them (they are already redacted).
- Separate facts from hypotheses. Give each likely cause a confidence: high, medium or low, and say why.
- Compare against a normal period (compare_windows) before calling something abnormal.
- Check whether other providers or hosts were affected in the same window; it decides where the problem is.
- Be efficient: a handful of targeted tool calls per incident is enough.

Write the final report in Markdown with these sections:
# Incident report
## Summary (one line per incident, most severe first)
## Timeline (table)
## One section per incident: what happened, impact (numbers), evidence (lines), likely cause with confidence, next checks
## Open questions (what the logs cannot answer)
"""


class MessagesClient(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


@dataclass
class InvestigationResult:
    report: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_early: bool = False


def _block_to_dict(block: Any) -> dict[str, Any]:
    t = getattr(block, "type", None)
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    raise ValueError(f"unexpected content block type: {t!r}")


class ClaudeInvestigator:
    def __init__(self, client: MessagesClient, toolbox: Toolbox, model: str = DEFAULT_MODEL,
                 max_turns: int = 15, max_tokens: int = 4096, max_tool_chars: int = 8000):
        self.client = client
        self.toolbox = toolbox
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.max_tool_chars = max_tool_chars

    def investigate(self, findings: list[Finding], ctx: ReportContext) -> InvestigationResult:
        intro = (
            f"Log source: {ctx.source}\n"
            f"Period: {ctx.first_ts} to {ctx.last_ts}\n"
            f"Events: {ctx.events} parsed, {ctx.unparsed} unparsed\n\n"
            f"Detector findings (JSON):\n{json.dumps([f.to_dict() for f in findings], indent=2)}\n\n"
            "Investigate each finding and write the incident report."
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": intro}]
        result = InvestigationResult(report="")

        for turn in range(1, self.max_turns + 1):
            resp = self.client.create(
                model=self.model, max_tokens=self.max_tokens, system=SYSTEM_PROMPT,
                tools=TOOL_SPECS, messages=messages,
            )
            result.turns = turn
            usage = getattr(resp, "usage", None)
            if usage is not None:
                result.input_tokens += getattr(usage, "input_tokens", 0) or 0
                result.output_tokens += getattr(usage, "output_tokens", 0) or 0

            content = [_block_to_dict(b) for b in resp.content]
            messages.append({"role": "assistant", "content": content})
            tool_uses = [b for b in content if b["type"] == "tool_use"]

            if not tool_uses:
                result.report = "\n".join(b["text"] for b in content if b["type"] == "text").strip()
                return result

            results = []
            for tu in tool_uses:
                output = self.toolbox.call(tu["name"], tu["input"] or {})
                if len(output) > self.max_tool_chars:
                    output = output[: self.max_tool_chars] + " ... [truncated]"
                result.tool_calls.append({"name": tu["name"], "input": tu["input"]})
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": output})
            messages.append({"role": "user", "content": results})

        # Budget exhausted. The last message is the user's tool results; add the instruction to it
        # (two user messages in a row are not allowed) and forbid further tool calls.
        result.stopped_early = True
        messages[-1]["content"].append(
            {"type": "text", "text": "Tool budget reached. Write the final report now with what you have."}
        )
        resp = self.client.create(model=self.model, max_tokens=self.max_tokens, system=SYSTEM_PROMPT,
                                  tools=TOOL_SPECS, tool_choice={"type": "none"}, messages=messages)
        result.report = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return result


def anthropic_client() -> MessagesClient:
    """Create a real client. Requires `pip install anthropic` and ANTHROPIC_API_KEY."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Claude mode needs the anthropic package: pip install -e '.[llm]'") from exc
    return anthropic.Anthropic().messages
