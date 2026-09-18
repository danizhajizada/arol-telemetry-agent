# Agent Decision Flow

This document explains how a user's question becomes an answer in the
AROL telemetry agent - the core "agentic" piece of the system.

## Overview

```
User question (free text)
        |
        v
System prompt + tool descriptions sent to the LLM
        |
        v
LLM decides: answer directly, OR request one or more tool calls
        |
        v
   [if tool_use]
        |
        v
Real Python function executes (pandas/Polars on closures/readings)
        |
        v
Result sent back to the LLM as plain data (JSON)
        |
        v
LLM decides: enough information now? -> write final report
             OR: still need more -> request another tool (loop)
        |
        v
Structured report returned to the user
```

## What the LLM actually sees

The LLM never has direct access to the data. On every call it receives:

1. **The system prompt** (`src/agent/orchestrator.py`, `SYSTEM_PROMPT`) -
   defines the agent's role, the required report structure (Goal, Data
   used, Analyses executed, Findings, Confidence/limits, Suggested next
   checks), and an explicit instruction not to invent numbers.
2. **The tool schemas** (`src/agent/tools.py`, `TOOL_SCHEMAS`) - a list
   of plain-text descriptions of every available function: its name,
   what it does, when to use it, and what parameters it accepts. No
   code, no data - just descriptions.
3. **The conversation so far** - the original question, plus (in later
   rounds) any tool results already returned.

The LLM's only two possible actions are: request a tool call, or write
final text. It cannot execute code, query the database, or see raw data
directly - every number it uses comes from a tool result it explicitly
requested.

## The tool-calling loop

Implemented in `run_agent()` (`orchestrator.py`). Each iteration:

1. Send the current conversation + tool schemas to the LLM.
2. Check `response.stop_reason`:
   - **Not `tool_use`** -> the LLM has finished reasoning and written its
     final report. Return that text. Loop ends.
   - **`tool_use`** -> the LLM has requested one or more tool calls.
     Continue to step 3.
3. For each requested tool call, look up the real function in
   `TOOL_FUNCTIONS` (`tools.py`) by name, and execute it against the
   actual data (`closures`, or `readings` for idle-related tools).
4. Convert each function's return value to JSON and send it back to the
   LLM as a "tool result" message.
5. Loop back to step 1 - the LLM now has the new information and decides
   whether it's enough, or whether another tool call is needed.

A hard cap (`max_tool_call_rounds`, default 5) prevents an infinite loop
if the LLM never settles on a final answer.

## Multi-step reasoning: a real example

Question: *"which head has the most problems and why?"*

This single question triggered a 6-tool, 3-round chain
(`sample_reports/real_data/01_multi_tool_root_cause_h29_h30.md`):

1. `success_rate_per_head` -> identifies H29 as the worst performer
2. `torque_stats_per_head` -> checks if H29's torque is abnormal (it isn't)
3. `detect_drift` -> checks for gradual degradation (none found)
4. `zscore_anomalies` -> checks for extreme individual outliers (none)
5. `success_rate_over_time` (head_id=H29) -> breaks failures down by day,
   finds 49 of 117 failures landed on a single day (2026-02-25)
6. `idle_time` -> rules out downtime as an alternative explanation

No step here was hardcoded - the LLM decided, at each point, whether the
evidence so far was sufficient or whether another angle needed checking.
This is hypothesis elimination (torque? drift? anomalies? downtime? -
each ruled out in turn) rather than a fixed, scripted sequence.

## Graceful failure

Two layers protect against bad input or tool errors, both tested against
real cases:

**Empty/invalid input**, before any API call is made:
```python
if not user_request or not user_request.strip():
    return "Please provide a question - I received an empty request."
```

**Tool execution failures** never crash the loop or propagate an
exception back to the user. `_run_tool()` wraps every call:
```python
try:
    result = TOOL_FUNCTIONS[name](closures, **tool_input)
    return json.dumps(result, default=str)
except Exception as exc:
    return json.dumps({"error": f"Tool '{name}' failed: {exc}"})
```
The LLM receives the error as a normal tool result and can explain the
failure to the user, or try a different approach, rather than the
program terminating.

**Out-of-scope questions** are handled by the LLM itself, not by code -
since it only has the tools described to it, a question with no matching
tool (e.g. "what's the weather like?") is answered honestly ("I don't
have a tool for that") rather than forcing an unrelated tool call or
fabricating an answer. Confirmed directly in testing multiple times.

## Why this design, not a fixed set of commands

An earlier, simpler design considered hardcoding a handful of expected
questions to specific tool calls. This was rejected because:

- Real questions are phrased in many different ways ("what's the
  average torque" vs "how much torque is applied on average" should
  both work identically) - a fixed mapping would need to anticipate
  every phrasing.
- Complex questions genuinely need multiple tools in sequence, decided
  dynamically based on what earlier results show - not knowable in
  advance from the question text alone.
- The grading criteria explicitly value "clear tool-use flow" as
  evidence of a real agent, not a disguised if/else chain.

## Adding a new tool

Three things always stay in sync:

1. **The function** - lives in the analytics layer (`src/analytics/`)
   for KPI/statistical/plotting functions, or the closure-detection
   layer (`src/closure_detection/detector.py`) for raw event-detection
   logic. Takes `closures` or `readings` as its first argument, returns
   a small, JSON-serializable dict or list - never the full raw table
   (returning millions of rows to the LLM would be both slow and
   unusable as context).
2. **The schema entry** - added to `TOOL_SCHEMAS` in `tools.py`, with a
   clear description of what the tool does and when to use it. This
   description is the only thing the LLM ever sees; a vague description
   directly causes wrong tool selection.
3. **The wiring** - one line in `TOOL_FUNCTIONS` mapping the tool name
   to the real function, using explicit `kw.get(...)` calls for
   parameters rather than blindly forwarding `**kw` (a past bug: an
   unexpected `config` keyword crashed a tool that forwarded `**kw`
   directly to a function that didn't accept it - now avoided by naming
   each expected parameter explicitly).

Because the function, its schema, and its wiring are three separate,
loosely-coupled pieces, new analysis capabilities can be added without
touching the orchestration loop itself (`run_agent()` in
`orchestrator.py` never changes) - only `tools.py` and the new function's
own module are affected.
