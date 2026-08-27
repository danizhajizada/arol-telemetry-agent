"""
Owned by Person C, but every entry here must match a real function Person B
wrote (see team_rules.md section 2.2/2.3). If B changes a function's
arguments, update TOOL_SCHEMAS and TOOL_FUNCTIONS here in the same day.

TOOL_SCHEMAS is what gets sent to the LLM - plain descriptions, no code.
TOOL_FUNCTIONS maps each tool name back to the real Python function that
actually runs on the closures dataframe.
"""
from src.analytics import kpi, trend, anomaly, correlation, plots

_READINGS_CONFIG = None


def set_readings_config(config: dict) -> None:
    """Called once at the start of ask/report/chat, before any question
    is answered. Idle-related tools (idle_time, machine_idle_periods)
    load readings lazily and directly from this config when actually
    called, rather than the app eagerly loading readings up front for
    every question regardless of whether it's needed."""
    global _READINGS_CONFIG
    _READINGS_CONFIG = config


def _plots_dir(config: dict | None) -> str:
    """Resolves the plot output directory from config; falls back to a
    default if config is missing the key (e.g. in ad-hoc calls/tests)."""
    if config and "output" in config:
        return config["output"].get("plots_dir", "output/plots/")
    return "output/plots/"


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
            "relative to that head's normal range. Use for anomaly/outlier "
            "questions. Returns at most `limit` rows, the most extreme first "
            "- on a large dataset there can be far more flagged events than "
            "that, so a raised threshold narrows results more reliably than "
            "a raised limit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "description": "z-score threshold, default 3.0"},
                "limit": {"type": "integer", "description": "max rows to return, most severe first, default 50 (capped at 500)"},
            },
        },
    },
       {
        "name": "success_rate_over_time",
        "description": (
            "Returns success rate broken down by time period (daily by "
            "default). Optionally restrict to one head to check whether "
            "that head's failures cluster in a specific time window. Use "
            "for questions about how success rate evolved over time, "
            "daily/hourly breakdowns, abnormal time intervals, or "
            "per-head failure timing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "freq": {
                    "type": "string",
                    "description": "pandas offset alias for the time bucket, e.g. 'D' for daily, 'h' for hourly (default 'D')",
                },
                "head_id": {
                    "type": "string",
                    "description": "optional - restrict to one head, e.g. 'H29'",
                },
            },
        },
    },
    {
        "name": "torque_distribution",
        "description": (
            "Returns a histogram (bin edges + counts) of applied torque "
            "values. Use for questions asking to show or describe the torque "
            "distribution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bins": {"type": "integer", "description": "number of histogram bins, default 10"},
                "successful_only": {
                    "type": "boolean",
                    "description": "restrict to successful closures only (default true)",
                },
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

    {
        "name": "torque_stats_per_head",
        "description": (
            "Returns average/min/max/standard deviation of applied torque, "
            "broken down per head. Omit head_id to get all 36 heads at "
            "once (use for comparing heads or finding which head has "
            "highest/lowest torque variability); pass head_id to get "
            "stats for just that one head."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "successful_only": {
                    "type": "boolean",
                    "description": "restrict to successful closures only (default true)",
                },
                "head_id": {
                    "type": "string",
                    "description": "optional - restrict to a single head (e.g. 'H01'); omit for all heads",
                },
            },
        },
    },

   {
    "name": "plot_torque_over_time",
    "description": (
        "Saves a scatter plot of applied torque over time for successful "
        "closures. Optionally restrict to one head and/or a date range "
        "(e.g. a specific month). Use for questions asking to plot/chart/"
        "visualize torque over time, optionally for a specific head or period."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "head_id": {"type": "string", "description": "optional - restrict to one head, e.g. 'H01'"},
            "start_date": {"type": "string", "description": "optional - ISO date, e.g. '2026-03-01'"},
            "end_date": {"type": "string", "description": "optional - ISO date, e.g. '2026-03-31'"},
        },
    },
},
    {
        "name": "plot_torque_histogram",
        "description": (
            "Renders and saves a histogram of applied torque values, and returns "
            "the file path. Use when the user asks to plot, chart, show, or "
            "visualize the torque distribution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bins": {"type": "integer", "description": "number of histogram bins, default 20"},
                "successful_only": {
                    "type": "boolean",
                    "description": "restrict to successful closures only (default true)",
                },
            },
        },
    },
    {
        "name": "plot_success_rate_per_head",
        "description": (
            "Renders and saves a bar chart of success rate per head, sorted "
            "worst to best, and returns the file path. Use when the user asks "
            "to plot, chart, show, or visualize per-head success rate."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "plot_failed_closures_over_time",
        "description": (
            "Renders and saves a bar chart of failed closure counts over time "
            "(daily by default), and returns the file path. Use when the user "
            "asks to plot, chart, show, or visualize failures over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "freq": {
                    "type": "string",
                    "description": "pandas offset alias for the time bucket, e.g. 'D' for daily, 'h' for hourly (default 'D')",
                }
            },
        },
    },
    {
        "name": "plot_dashboard_summary",
        "description": (
            "Renders and saves a combined dashboard (success rate per head, "
            "torque histogram, torque over time, failed closures per day) as "
            "one image, and returns the file path. Use for broad 'show me a "
            "dashboard' or 'summarize visually' requests."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
    "name": "plot_failures_per_head",
    "description": (
        "Saves a bar chart of raw failure count per head (not success "
        "rate percentage, which is uninformative since it rounds to ~100% "
        "for every head). Use for questions asking to plot/chart failures "
        "or problems per head."
    ),
    "input_schema": {"type": "object", "properties": {}},
    },
    {
    "name": "idle_time",
    "description": (
        "Reports total and average idle time per head (that specific "
        "head stopped, others may still be running), plus how many "
        "separate idle periods. Use for questions about idle time or "
        "downtime for a specific head or across heads."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sustained_seconds": {"type": "integer", "description": "minimum idle duration in seconds, default 300"}
        },
    },
   },
   {
    "name": "machine_idle_periods",
    "description": (
        "Reports periods when the ENTIRE machine (all heads at once) was "
        "idle together, with exact start/end times. Use for questions "
        "about full-line downtime, shutdowns, or confirming whether a "
        "shared event affected all heads simultaneously."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sustained_seconds": {"type": "integer", "description": "minimum idle duration in seconds, default 300"}
        },
     },
    },

]

TOOL_FUNCTIONS = {
    "success_rate": lambda closures, config=None, **kw: kpi.success_rate(closures),
    "success_rate_per_head": lambda closures, config=None, **kw: kpi.success_rate_per_head(closures).to_dict(orient="records"),
    "torque_stats": lambda closures, config=None, **kw: kpi.torque_stats(closures, **kw),
    "torque_stats_per_head": lambda closures, config=None, **kw: kpi.torque_stats_per_head(closures, **kw),
    "capping_speed": lambda closures, config=None, **kw: kpi.capping_speed_incremental(closures).groupby("head_id")["capping_speed_pph"].last().round(1).to_dict(),
    "success_rate_over_time": lambda closures, **kw: kpi.success_rate_over_time(closures, freq=kw.get("freq", "D"), head_id=kw.get("head_id")).to_dict(orient="records"),
    "torque_distribution": lambda closures, config=None, **kw: kpi.torque_distribution(closures, **kw).to_dict(orient="records"),
    "detect_drift": lambda closures, config=None, **kw: trend.detect_drift(closures, window=kw.get("window", 50)).to_dict(orient="records"),
    "zscore_anomalies": lambda closures, config=None, **kw: anomaly.zscore_anomalies(closures, threshold=kw.get("threshold", 3.0), limit=kw.get("limit", 50)).to_dict(orient="records"),
    "head_correlation": lambda closures, config=None, **kw: correlation.head_torque_correlation(closures).to_dict(),
    "plot_torque_over_time": lambda closures, **kw: plots.plot_torque_over_time(closures, output_dir="output/plots", head_id=kw.get("head_id"), start_date=kw.get("start_date"), end_date=kw.get("end_date")),
    "plot_torque_histogram": lambda closures, config=None, **kw: plots.plot_torque_histogram(
        closures, output_dir=_plots_dir(config), **kw
    ),
    "plot_success_rate_per_head": lambda closures, config=None, **kw: plots.plot_success_rate_per_head(
        closures, output_dir=_plots_dir(config)
    ),
    "plot_failed_closures_over_time": lambda closures, config=None, **kw: plots.plot_failed_closures_over_time(
        closures, output_dir=_plots_dir(config), **kw
    ),
    "plot_dashboard_summary": lambda closures, config=None, **kw: plots.plot_dashboard_summary(
        closures, output_dir=_plots_dir(config)
    ),
    "plot_failures_per_head": lambda closures, **kw: plots.plot_failures_per_head(closures, output_dir="output/plots"),
    "idle_time": lambda closures, **kw: kpi.idle_time_per_head(_READINGS_CONFIG, sustained_seconds=kw.get("sustained_seconds", 300)),
    "machine_idle_periods": lambda closures, **kw: kpi.machine_idle_periods_summary(_READINGS_CONFIG, sustained_seconds=kw.get("sustained_seconds", 300)),
}
