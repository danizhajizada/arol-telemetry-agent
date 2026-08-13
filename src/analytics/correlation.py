"""
Correlation checks among heads (e.g. does head 1's torque behavior
correlate with head 5's), useful for spotting mechanically linked issues.
"""
import pandas as pd


def head_torque_correlation(closures: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of torque values across heads, aligned
    by closure order (not wall-clock time, since heads close at different
    rates).

    Restricted to status_label == "Closure OK" before pivoting/aligning.
    Without this, heads that happen to enter "No Load" (app_torque ~ 0) at
    the same time would show artificially high correlation that reflects
    shared idle periods rather than a real mechanical relationship between
    their closure torque.
    """
    closures = closures[closures["status_label"] == "Closure OK"]
    pivoted = closures.pivot_table(
        index=closures.groupby("head_id").cumcount(),
        columns="head_id",
        values="app_torque",
    )
    return pivoted.corr()
