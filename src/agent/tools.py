"""
Owned by Person C, but every entry here must match a real function Person B
wrote (see team_rules.md section 2.2/2.3). If B changes a function's
arguments, update TOOL_SCHEMAS and TOOL_FUNCTIONS here in the same day.

TOOL_SCHEMAS is what gets sent to the LLM - plain descriptions, no code.
TOOL_FUNCTIONS maps each tool name back to the real Python function that
actually runs on the closures dataframe.
"""
from src.analytics import kpi, trend, anomaly, correlation

TOOL_SCHEMAS = [
    {
        "name": "success_rate",
        "description": (
            "Returns overall total/successful/failed closure counts and the "
            "success rate percentage. Use for questions about overall process "
            "quality or how many/what percent of caps succeeded or failed."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "success_rate_per_head",
        "description": (
            "Returns a per-head breakdown of closure counts and success rate. "
            "Use for questions comparing heads, which head performs worst, or "
            "per-head failure counts."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "torque_stats",
        "description": (
            "Returns average/min/max/standard deviation of applied torque. "
            "Use for questions about torque values or torque consistency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "successful_only": {
                    "type": "boolean",
                    "description": "restrict to successful closures only (default true)",
                }
            },
        },
    },
    {
        "name": "capping_speed",
        "description": (
            "Returns capping speed in pieces/hour per head, computed as an "
            "incremental average. Use for throughput or production-rate questions."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "detect_drift",
        "description": (
            "Flags heads whose average torque has drifted significantly over "
            "the observed period. Use for questions about trends, drift, or "
            "whether something is getting worse/better over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "integer", "description": "rolling window size in closures"}
            },
        },
    },
    {
        "name": "zscore_anomalies",
        "description": (
            "Flags individual closures with unusually high or low torque "
            "relative to that head's normal range. Use for anomaly/outlier questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "description": "z-score threshold, default 3.0"}
            },
        },
    },
    {
        "name": "head_correlation",
        "description": (
            "Returns pairwise torque correlation between heads. Use for "
            "questions comparing behavior between two or more specific heads."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

TOOL_FUNCTIONS = {
    "success_rate": lambda closures, **kw: kpi.success_rate(closures),
    "success_rate_per_head": lambda closures, **kw: kpi.success_rate_per_head(closures).to_dict(orient="records"),
    "torque_stats": lambda closures, **kw: kpi.torque_stats(closures, **kw),
    "capping_speed": lambda closures, **kw: kpi.capping_speed_incremental(closures).to_dict(orient="records"),
    "detect_drift": lambda closures, **kw: trend.detect_drift(closures, window=kw.get("window", 50)).to_dict(orient="records"),
    "zscore_anomalies": lambda closures, **kw: anomaly.zscore_anomalies(closures, threshold=kw.get("threshold", 3.0)).to_dict(orient="records"),
    "head_correlation": lambda closures, **kw: correlation.head_torque_correlation(closures).to_dict(),
}
