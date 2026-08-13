"""
Simple statistical anomaly detection (z-score thresholding) on torque
values. Deterministic and dependency-light so it's a reliable tool for the
agent to call.
"""
import pandas as pd


def zscore_anomalies(closures: pd.DataFrame, threshold: float = 3.0, limit: int = 50) -> pd.DataFrame:
    """Flag closures whose torque is more than `threshold` standard
    deviations from that head's mean torque, returning at most `limit`
    rows (the most extreme by |z-score|).

    Restricted to status_label == "Closure OK" before computing the
    z-score. The closures table also contains "No Load" cycles (app_torque
    ~ 0) and known rejects; including them would make each head's torque
    distribution bimodal (~0 Nm and ~2 Nm), which breaks the z-score's
    assumption of a roughly unimodal distribution and produces meaningless
    flags. Restricting to Closure OK isolates real closures so the z-score
    actually measures deviation within otherwise-normal capping torque.

    On a large dataset, the number of closures above `threshold` can run
    into the thousands - far more than a caller (or an LLM tool result)
    should receive at once - so this returns only the most severe `limit`
    rows rather than every flagged event.
    """
    df = closures[closures["status_label"] == "Closure OK"].copy()
    df["torque_zscore"] = df.groupby("head_id")["app_torque"].transform(
        lambda s: (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) > 0 else 0
    )
    anomalies = df[df["torque_zscore"].abs() >= threshold]
    anomalies = anomalies.reindex(
        anomalies["torque_zscore"].abs().sort_values(ascending=False).index
    )
    limit = max(1, min(limit, 500))
    return anomalies[
        ["timestamp", "head_id", "app_torque", "torque_zscore", "status_label"]
    ].head(limit).reset_index(drop=True)
