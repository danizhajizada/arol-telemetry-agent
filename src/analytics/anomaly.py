"""
Simple statistical anomaly detection (z-score thresholding) on torque
values. Deterministic and dependency-light so it's a reliable tool for the
agent to call.
"""
import pandas as pd


def zscore_anomalies(closures: pd.DataFrame, threshold: float = 3.0) -> pd.DataFrame:
    """Flag closures whose torque is more than `threshold` standard
    deviations from that head's mean torque."""
    df = closures.copy()
    df["torque_zscore"] = df.groupby("head_id")["app_torque"].transform(
        lambda s: (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) > 0 else 0
    )
    anomalies = df[df["torque_zscore"].abs() >= threshold]
    return anomalies[
        ["timestamp", "head_id", "app_torque", "torque_zscore", "status_label"]
    ].reset_index(drop=True)
