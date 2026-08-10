"""
Detects real capping-closure events from the long-format telemetry.

Core rule: a head has "closed" a cap when its Count at time t differs from
its Count at time t-1. Every second where Count is unchanged is a
redundant poll, not a new event, and is dropped.

Also classifies each detected closure using the status-code table from
config.yaml, and detects sustained idle periods per head based on the
"No Load" status.

Note: dataset is single-machine, so grouping is by head_id only.
"""
import pandas as pd


def detect_closures(long_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the per-second long-format stream into one row per real
    closure event, per head_id."""
    df = long_df.sort_values(["head_id", "timestamp"]).copy()
    df["count_prev"] = df.groupby("head_id")["count"].shift(1)
    df["is_closure"] = (
    (df["count"] != df["count_prev"])
    & (df["count"] > 0)
    & (df["count_prev"] > 0)
)
    df.loc[df["count_prev"].isna(), "is_closure"] = False

    closures = df[df["is_closure"]].copy()
    return closures[
        ["timestamp", "head_id", "count", "app_torque", "status"]
    ].reset_index(drop=True)


def classify_status(closures: pd.DataFrame, status_codes: dict) -> pd.DataFrame:
    """Attach human-readable label and reject flag to each closure event."""
    closures = closures.copy()
    closures["status_label"] = closures["status"].map(
        lambda s: status_codes.get(int(s), {}).get("label", f"Unknown ({s})")
    )
    closures["is_reject"] = closures["status"].map(
        lambda s: status_codes.get(int(s), {}).get("reject", False)
    )
    return closures


def detect_idle_periods(
    long_df: pd.DataFrame, idle_status_code: int, sustained_seconds: int
) -> pd.DataFrame:
    """Identify sustained idle windows per head, based on the configured
    'No Load' status persisting for at least sustained_seconds."""
    df = long_df.sort_values(["head_id", "timestamp"]).copy()
    df["is_idle_status"] = df["status"] == idle_status_code
    df["run_id"] = (
        df["is_idle_status"] != df.groupby("head_id")["is_idle_status"].shift(1)
    ).cumsum()

    idle_runs = (
        df[df["is_idle_status"]]
        .groupby(["head_id", "run_id"])
        .agg(start=("timestamp", "min"), end=("timestamp", "max"), n_rows=("timestamp", "count"))
        .reset_index()
    )
    idle_runs["duration_seconds"] = (idle_runs["end"] - idle_runs["start"]).dt.total_seconds()

    return idle_runs[idle_runs["duration_seconds"] >= sustained_seconds].drop(columns=["run_id"])
