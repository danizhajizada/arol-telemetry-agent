"""
Deterministic KPI functions computed on classified closure events.
These are exposed as "tools" to the orchestrating agent (see agent/tools.py).

Note on "successful": the closures table includes both real capping cycles
(status_label "Closure OK" or a reject label) and "No Load" cycles, where the
head cycled but no cap was present (app_torque ~ 0, is_reject is False since
it is not a failure, just an empty cycle). Torque-oriented functions below
filter to "Closure OK" specifically (not just "not is_reject") so that
zero-torque No Load rows don't distort averages/histograms/anomaly stats.
success_rate* functions intentionally still count "not is_reject" as
successful, which currently means No Load cycles count as successful
closures — this is a known open question for the team (see B's findings
doc), not something silently changed here.
"""
import numpy as np
import pandas as pd


def success_rate(closures: pd.DataFrame) -> dict:
    """Overall total/successful/failed closure counts and success rate percentage.

    "Successful" means not flagged as a reject (is_reject == False). This
    includes "No Load" cycles (head cycled with no cap present), which are
    not failures but are also not real capping operations — see module note.
    """
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
    """Per-head breakdown of closure counts and success rate.

    Same "not is_reject" definition of success as success_rate() — see
    module note on No Load cycles.
    """
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
    successful closures only (default).

    When successful_only=True, restricts to status_label == "Closure OK"
    rather than just "not is_reject", because "No Load" rows are not
    rejects but have app_torque ~ 0 and would otherwise pull every torque
    statistic toward zero.
    """
    if successful_only:
        data = closures[closures["status_label"] == "Closure OK"]
    else:
        data = closures

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
    head's stats as a dict; otherwise returns all heads as a list.

    When successful_only=True, restricts to status_label == "Closure OK" —
    see torque_stats() for why "not is_reject" alone is not enough (it would
    include zero-torque "No Load" rows and skew every head's stats toward
    zero).
    """
    if successful_only:
        data = closures[closures["status_label"] == "Closure OK"]
    else:
        data = closures
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


def success_rate_over_time(closures: pd.DataFrame, freq: str = "D", head_id: str = None) -> pd.DataFrame:
    """Success rate broken down by time period (default daily), for spotting
    trends or specific bad days/hours; pass freq='h' for an hourly trend.
    Optionally restrict to a single head via head_id, to check whether
    that head's failures cluster in a specific time window.

    Same "not is_reject" definition of success as success_rate() - see
    module note on No Load cycles.
    """
    df = closures[closures["head_id"] == head_id] if head_id is not None else closures.copy()
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
    restricted to successful closures only (default).

    When successful_only=True, restricts to status_label == "Closure OK" —
    see torque_stats() for why "not is_reject" alone is not enough (it would
    include zero-torque "No Load" rows and skew every bin toward zero).
    """
    if successful_only:
        data = closures[closures["status_label"] == "Closure OK"]
    else:
        data = closures

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
    average updated as each new closure arrives.

    Uses count_increment (the real counter advance recorded by Person A's
    detector) rather than the number of closure rows, because a single row
    can represent several physical cycles at once when the counter jumps by
    more than 1 (e.g. after a telemetry gap). Counting rows instead of
    count_increment would understate throughput whenever those jumps occur.
    The first row of each head has zero elapsed time by construction, so its
    speed is undefined (NaN).
    """
    df = closures.sort_values(["head_id", "timestamp"]).copy()
    grouped = df.groupby("head_id")

    start_time = df.groupby("head_id")["timestamp"].transform("min")
    elapsed_hours = (df["timestamp"] - start_time).dt.total_seconds() / 3600.0
    elapsed_hours = elapsed_hours.replace(0, float("nan"))
    pieces_cumulative = df.groupby("head_id")["count_increment"].cumsum()

    df["capping_speed_pph"] = pieces_cumulative / elapsed_hours
    return df[["timestamp", "head_id", "capping_speed_pph"]]


def idle_time_per_head(config: dict, sustained_seconds: int = 300) -> dict:
    """Total/average idle time per head. Uses a lazy Parquet scan,
    filtering to one head BEFORE loading into memory - keeps peak memory
    to one head's data (~7.6M rows) instead of the full readings table
    (~274M rows), which caused out-of-memory failures when all heads
    were processed together via an eager load + filter approach.
    Confirmed via testing: ~70s total for all 36 heads at full 90-day
    scale, versus 873s+ (with crashes) using the eager-load approach."""
    from pathlib import Path
    import polars as pl
    from src.closure_detection.detector import detect_idle_periods

    readings_dir = Path(config["database"]["path"]).parent / "readings"
    lazy_readings = pl.scan_parquet(str(readings_dir / "*.parquet"))
    heads = lazy_readings.select("head_id").unique().collect()["head_id"].to_list()

    all_idle_frames = []
    for head_id in heads:
        subset = lazy_readings.filter(pl.col("head_id") == head_id).collect()
        idle_df = detect_idle_periods(subset, idle_status_code=2, sustained_seconds=sustained_seconds)
        if not idle_df.is_empty():
            all_idle_frames.append(idle_df)
        del subset, idle_df

    if not all_idle_frames:
        return {}

    combined = pl.concat(all_idle_frames)
    summary = combined.group_by("head_id").agg([
        pl.col("duration_seconds").sum().alias("total_idle_seconds"),
        pl.col("duration_seconds").mean().alias("avg_idle_seconds"),
        pl.len().alias("idle_periods"),
    ])
    return {
        row["head_id"]: {
            "total_idle_minutes": round(row["total_idle_seconds"] / 60, 1),
            "avg_idle_minutes": round(row["avg_idle_seconds"] / 60, 1),
            "idle_periods": row["idle_periods"],
        }
        for row in summary.to_dicts()
    }

def machine_idle_periods_summary(config: dict, sustained_seconds: int = 300) -> list:
    """Summary of times the ENTIRE machine (all heads simultaneously) went
    idle together. Processes data week-by-week (not all 90 days at once)
    to keep memory manageable - detect_machine_idle_periods() needs all
    heads' data at each timestamp simultaneously, so unlike
    idle_time_per_head it can't be chunked by head; time-window chunking
    instead. Confirmed via testing: ~16s total, 366 idle periods found
    across the full 90-day dataset, versus an out-of-memory crash when
    processing all 90 days in one pass."""
    from pathlib import Path
    from datetime import timedelta
    import polars as pl
    from src.closure_detection.detector import detect_machine_idle_periods

    readings_dir = Path(config["database"]["path"]).parent / "readings"
    lazy_readings = pl.scan_parquet(str(readings_dir / "*.parquet")).with_columns(
        pl.lit("M1").alias("machine_id")
    )

    date_range = lazy_readings.select(
        pl.col("timestamp").min().alias("min_ts"),
        pl.col("timestamp").max().alias("max_ts"),
    ).collect()
    start_date = date_range["min_ts"][0]
    end_date = date_range["max_ts"][0]

    all_idle_frames = []
    current = start_date
    while current <= end_date:
        window_end = current + timedelta(days=7)
        chunk = lazy_readings.filter(
            (pl.col("timestamp") >= current) & (pl.col("timestamp") < window_end)
        ).collect()

        if not chunk.is_empty():
            idle_df = detect_machine_idle_periods(chunk, idle_status_code=2, sustained_seconds=sustained_seconds)
            if not idle_df.is_empty():
                all_idle_frames.append(idle_df)
            del chunk, idle_df

        current = window_end

    if not all_idle_frames:
        return []

    combined = pl.concat(all_idle_frames)
    return [
        {
            "machine_id": row["machine_id"],
            "start": str(row["start"]),
            "end": str(row["end"]),
            "duration_minutes": round(row["duration_seconds"] / 60, 1),
        }
        for row in combined.to_dicts()
    ]