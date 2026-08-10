"""
Exposes the deterministic analytics functions (src/analytics/*) as MCP
tools, so an LLM-based orchestrator can call them by name instead of the
agent needing to write pandas code itself.

This is a skeleton - wire up the real MCP SDK server here. Each tool
should take simple, serializable arguments (machine_id, date range, etc.)
and return JSON-serializable results, since the LLM only sees text.
"""
from src.analytics import kpi, trend, anomaly, correlation

# Pseudocode / structure - replace with the actual `mcp` SDK server object.
# from mcp.server import Server
# server = Server("arol-telemetry-tools")

TOOLS = {
    "success_rate": kpi.success_rate,
    "success_rate_per_head": kpi.success_rate_per_head,
    "torque_stats": kpi.torque_stats,
    "capping_speed": kpi.capping_speed_incremental,
    "moving_average": trend.moving_average,
    "detect_drift": trend.detect_drift,
    "zscore_anomalies": anomaly.zscore_anomalies,
    "head_correlation": correlation.head_torque_correlation,
}

# TODO: register each entry in TOOLS as an MCP tool with a JSON schema
# description, so the orchestrating LLM can discover and call them.
