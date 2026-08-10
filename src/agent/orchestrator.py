"""
The "report agent": takes a free-text request, lets the LLM decide which
tools (from agent/tools.py) to call and in what order, and returns the
final text report. See team_rules.md section 2.3 before changing tool
names here.
"""
import json
import logging

import anthropic
import pandas as pd

from src.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an analysis agent for AROL capping-machine telemetry. "
    "Use the available tools to answer the user's question about closure "
    "events, torque, success rate, or trends. Once you have enough "
    "information, write your final answer as a short structured report "
    "with these sections: Goal, Data used, Analyses executed, Findings, "
    "Confidence/limits, Suggested next checks. Be concise and only state "
    "what the tool results actually support - do not invent numbers."
)


def _run_tool(name: str, tool_input: dict, closures: pd.DataFrame) -> str:
    """Runs one tool and returns a JSON string result, or a clear error
    message if the tool fails - never raises, so the LLM always gets a
    usable response to reason about (graceful failure)."""
    if name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool '{name}'."})

    try:
        result = TOOL_FUNCTIONS[name](closures, **tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.warning("Tool '%s' failed with input %s: %s", name, tool_input, exc)
        return json.dumps({"error": f"Tool '{name}' failed: {exc}"})


def run_agent(user_request: str, closures: pd.DataFrame, config: dict) -> str:
    """Runs the full tool-calling loop and returns the LLM's final text report."""
    client = anthropic.Anthropic()
    llm_config = config["llm"]
    messages = [{"role": "user", "content": user_request}]

    for _ in range(llm_config["max_tool_call_rounds"]):
        response = client.messages.create(
            model=llm_config["model"],
            max_tokens=llm_config["max_tokens"],
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return next(
                (b.text for b in response.content if b.type == "text"),
                "The agent did not return a text response.",
            )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            result_json = _run_tool(tool_use.name, tool_use.input, closures)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_json,
            })
        messages.append({"role": "user", "content": tool_results})

    return (
        "The agent reached the maximum number of tool-call rounds without "
        "producing a final answer. Try rephrasing a more specific question."
    )
