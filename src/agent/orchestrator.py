"""
The "report agent": takes a free-text request, lets the LLM decide which
tools (from agent/tools.py) to call and in what order, and returns the
final text report. See team_rules.md section 2.3 before changing tool
names here.
"""
import json
import logging
import time
from dataclasses import dataclass, field

import anthropic
import pandas as pd

from src.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Return value of run_agent(): the final text report plus any chart
    files a plotting tool saved along the way (empty if none were called)."""
    text: str
    generated_files: list[str] = field(default_factory=list)

SYSTEM_PROMPT = (
    "You are an analysis agent for AROL capping-machine telemetry. "
    "Use the available tools to answer the user's question about closure "
    "events, torque, success rate, or trends. Some tools render and save a "
    "chart instead of returning numbers directly (their name starts with "
    "'plot_') - use one of those whenever the user asks to plot, chart, "
    "show, or visualize something; report the file path it returns so the "
    "user knows where to find the image. Once you have enough information, "
    "write your final answer as a short structured report with these "
    "sections: Goal, Data used, Analyses executed, Findings, "
    "Confidence/limits, Suggested next checks. Be concise and only state "
    "what the tool results actually support - do not invent numbers."
)


def _run_tool(name: str, tool_input: dict, closures: pd.DataFrame, config: dict) -> tuple[str, str | None]:
    """Runs one tool and returns (JSON string result, generated file path or
    None). Never raises - a failure becomes an error message in the JSON, so
    the LLM always gets a usable response to reason about (graceful failure)."""
    if name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool '{name}'."}), None
    t0 = time.time()
    try:
        result = TOOL_FUNCTIONS[name](closures, config=config, **tool_input)
        elapsed = time.time() - t0
        logger.info("[TIMING] Tool '%s' took %.2fs", name, elapsed)
        generated_file = result.get("file") if isinstance(result, dict) else None
        return json.dumps(result, default=str), generated_file
    except Exception as exc:
        logger.warning("Tool '%s' failed with input %s: %s", name, tool_input, exc)
        return json.dumps({"error": f"Tool '{name}' failed: {exc}"}), None


def run_agent(user_request: str, closures: pd.DataFrame, config: dict) -> AgentResult:
    """Runs the full tool-calling loop and returns the LLM's final text
    report, plus the paths of any chart files generated along the way."""
    if not user_request or not user_request.strip():
        return AgentResult(text="Please provide a question - I received an empty request.")

    client = anthropic.Anthropic(api_key=config["llm"].get("ANTHROPIC_API_KEY"))
    llm_config = config["llm"]
    messages = [{"role": "user", "content": user_request}]
    generated_files: list[str] = []

    for _ in range(llm_config["max_tool_call_rounds"]):
        t0 = time.time()
        response = client.messages.create(
            model=llm_config["model"],
            max_tokens=llm_config["max_tokens"],
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        logger.info("[TIMING] LLM call took %.2fs", time.time() - t0)
        if response.stop_reason != "tool_use":
            text = next(
                (b.text for b in response.content if b.type == "text"),
                "The agent did not return a text response.",
            )
            return AgentResult(text=text, generated_files=generated_files)

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            return AgentResult(
                text="The agent indicated a tool call but none was found.",
                generated_files=generated_files,
            )

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            result_json, generated_file = _run_tool(tool_use.name, tool_use.input, closures, config)
            if generated_file:
                generated_files.append(generated_file)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_json,
            })
        messages.append({"role": "user", "content": tool_results})

    return AgentResult(
        text=(
            "The agent reached the maximum number of tool-call rounds without "
            "producing a final answer. Try rephrasing a more specific question."
        ),
        generated_files=generated_files,
    )