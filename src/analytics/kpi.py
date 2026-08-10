"""
Deterministic KPI functions computed on classified closure events.
These are exposed as "tools" to the orchestrating agent (see agent/tools.py).
"""
import pandas as pd


def success_rate(closures: pd.DataFrame) -> dict:
    """Overall total/successful/failed closure counts and success rate percentage."""
    total = len(closures)
    if total == 0:
        return {"total_closures": 0, "successful": 0, "failed": 0, "success_rate_pct": None}

    failed = int(closures["is_reject"].sum())
    successful = total - failed
    return {
        "total_closures": total,
        "successful": successful,
        "failed": failed,
        "success_rate_pct": round(100 * successful / total, 2),
    }


def success_rate_per_head(closures: pd.DataFrame) -> pd.DataFrame:
    """Per-head breakdown of closure counts and success rate."""
    grouped = closures.groupby("head_id").agg(
        total_closures=("is_reject", "count"),
        failed=("is_reject", "sum"),
    )
    grouped["successful"] = grouped["total_closures"] - grouped["failed"]
    grouped["success_rate_pct"] = (
        100 * grouped["successful"] / grouped["total_closures"]
    ).round(2)
    return grouped.reset_index()


def torque_stats(closures: pd.DataFrame, successful_only: bool = True) -> dict:
    """Average/min/max/std of applied torque, optionally filtered to
    successful closures only (default)."""
    data = closures[~closures["is_reject"]] if successful_only else closures
    if data.empty:
        return {"count": 0}

    return {
        "count": int(len(data)),
        "average_torque": round(float(data["app_torque"].mean()), 3),
        "min_torque": round(float(data["app_torque"].min()), 3),
        "max_torque": round(float(data["app_torque"].max()), 3),
        "std_torque": round(float(data["app_torque"].std()), 3),
    }


def capping_speed_incremental(closures: pd.DataFrame) -> pd.DataFrame:
    """Capping speed (pieces/hour) per head, using an incremental (running)
    average updated as each new closure arrives."""
    df = closures.sort_values(["head_id", "timestamp"]).copy()

    def _incremental(group: pd.DataFrame) -> pd.DataFrame:
        group = group.copy()
        start_time = group["timestamp"].iloc[0]
        elapsed_hours = (group["timestamp"] - start_time).dt.total_seconds() / 3600.0
        piece_index = pd.Series(range(1, len(group) + 1), index=group.index)
        group["capping_speed_pph"] = (piece_index / elapsed_hours.replace(0, pd.NA)).astype(float)
        return group

    return (
        df.groupby("head_id", group_keys=False)
        .apply(_incremental)[["timestamp", "head_id", "capping_speed_pph"]]
    )
