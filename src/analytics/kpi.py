"""
Deterministic KPI functions computed on classified closure events.
These are exposed as "tools" to the orchestrating agent (see agent/tools.py).
"""
import numpy as np
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

def torque_stats_per_head(closures: pd.DataFrame, successful_only: bool = True, head_id: str = None) -> dict | list:
    """Per-head torque stats. If head_id is given, returns just that
    head's stats as a dict; otherwise returns all heads as a list."""
    data = closures[~closures["is_reject"]] if successful_only else closures
    if head_id is not None:
        data = data[data["head_id"] == head_id]
        if data.empty:
            return {"count": 0}
        return {
            "head_id": head_id,
            "count": int(len(data)),
            "average_torque": round(float(data["app_torque"].mean()), 3),
            "min_torque": round(float(data["app_torque"].min()), 3),
            "max_torque": round(float(data["app_torque"].max()), 3),
            "std_torque": round(float(data["app_torque"].std()), 3),
        }

    return (
        data.groupby("head_id")["app_torque"]
        .agg(count="count", average_torque="mean", min_torque="min", max_torque="max", std_torque="std")
        .round(3)
        .reset_index()
        .to_dict(orient="records")
    )


def success_rate_over_time(closures: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Success rate broken down by time period (default daily), for spotting
    trends or specific bad days/hours; pass freq='h' for an hourly trend."""
    df = closures.copy()
    df["period"] = df["timestamp"].dt.floor(freq)
    grouped = df.groupby("period").agg(
        total_closures=("is_reject", "count"),
        failed=("is_reject", "sum"),
    )
    grouped["successful"] = grouped["total_closures"] - grouped["failed"]
    grouped["success_rate_pct"] = (
        100 * grouped["successful"] / grouped["total_closures"]
    ).round(2)
    return grouped.reset_index()


def torque_distribution(closures: pd.DataFrame, bins: int = 10, successful_only: bool = True) -> pd.DataFrame:
    """Histogram of applied torque values (bin edges + counts), optionally
    restricted to successful closures only (default)."""
    data = closures[~closures["is_reject"]] if successful_only else closures
    if data.empty:
        return pd.DataFrame(columns=["bin_start", "bin_end", "count"])

    counts, edges = np.histogram(data["app_torque"], bins=bins)
    return pd.DataFrame({
        "bin_start": edges[:-1].round(3),
        "bin_end": edges[1:].round(3),
        "count": counts,
    })


def capping_speed_incremental(closures: pd.DataFrame) -> pd.DataFrame:
    """Capping speed (pieces/hour) per head, using an incremental (running)
    average updated as each new closure arrives - per spec requirement.
    Vectorized (no groupby.apply) to avoid two real bugs found in an
    earlier version: (1) pd.NA -> float conversion crash on the first
    closure per head, where elapsed time is 0; (2) a pandas-version-
    dependent bug where groupby().apply() turned head_id into the index
    instead of a column."""
    df = closures.sort_values(["head_id", "timestamp"]).copy()
    grouped = df.groupby("head_id")

    start_time = grouped["timestamp"].transform("first")
    elapsed_hours = (df["timestamp"] - start_time).dt.total_seconds() / 3600.0
    piece_index = grouped.cumcount() + 1  # 1-based count of closures so far, per head

    speed = piece_index / elapsed_hours.replace(0, float("nan"))
    df["capping_speed_pph"] = speed.astype(float)

    return df[["timestamp", "head_id", "capping_speed_pph"]]

