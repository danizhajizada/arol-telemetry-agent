"""
Correlation checks among heads (e.g. does head 1's torque behavior
correlate with head 5's), useful for spotting mechanically linked issues.
"""
import pandas as pd


def head_torque_correlation(closures: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of torque values across heads, aligned
    by closure order (not wall-clock time, since heads close at different
    rates)."""
    pivoted = closures.pivot_table(
        index=closures.groupby("head_id").cumcount(),
        columns="head_id",
        values="app_torque",
    )
    return pivoted.corr()
