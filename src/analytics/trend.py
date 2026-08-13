"""
Trend analysis: moving averages and drift detection on torque values.

Both functions restrict to status_label == "Closure OK" before computing
anything. The closures table also contains "No Load" cycles (head cycled,
no cap present, app_torque ~ 0) and reject cycles; mixing those into a
rolling average of torque would make the trend track the changing mix of
cycle types instead of real torque drift on actual closures.
"""
import pandas as pd


def moving_average(closures: pd.DataFrame, window: int) -> pd.DataFrame:
    """Rolling mean of applied torque per head, over `window` closures.

    Computed only over status_label == "Closure OK" rows (see module note).
    """
    df = closures[closures["status_label"] == "Closure OK"]
    df = df.sort_values(["head_id", "timestamp"]).copy()
    df["torque_moving_avg"] = df.groupby("head_id")["app_torque"].transform(
        lambda s: s.rolling(window=window, min_periods=1).mean()
    )
    return df[["timestamp", "head_id", "app_torque", "torque_moving_avg"]]


def detect_drift(closures: pd.DataFrame, window: int = 50, drift_threshold: float = 0.1) -> pd.DataFrame:
    """Flag heads whose torque moving average has drifted by more than
    `drift_threshold` (fractional change) between the start and end of the
    observed period.

    Computed only over status_label == "Closure OK" rows (see module note),
    so a drop in No Load or reject frequency doesn't get misread as torque
    drift.
    """
    closures = closures[closures["status_label"] == "Closure OK"]
    results = []
    for head_id, group in closures.groupby("head_id"):
        group = group.sort_values("timestamp")
        rolling = group["app_torque"].rolling(window=window, min_periods=1).mean()
        if len(rolling) < 2 or rolling.iloc[0] == 0:
            continue
        drift_pct = (rolling.iloc[-1] - rolling.iloc[0]) / rolling.iloc[0]
        if abs(drift_pct) >= drift_threshold:
            results.append({
                "head_id": head_id,
                "start_avg_torque": round(float(rolling.iloc[0]), 3),
                "end_avg_torque": round(float(rolling.iloc[-1]), 3),
                "drift_pct": round(float(drift_pct * 100), 2),
            })
    return pd.DataFrame(results)
