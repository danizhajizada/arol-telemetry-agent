import pandas as pd
from src.analytics import kpi, trend, anomaly


def _sample_closures():
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=6, freq="min"),
        "head_id": ["H01", "H01", "H01", "H02", "H02", "H02"],
        "count": [1, 2, 3, 1, 2, 3],
        "app_torque": [2.5, 2.6, 2.4, 2.5, 2.5, 5.0],  # last H02 value is an outlier
        "status": [0, 0, 65, 0, 0, 0],
        "status_label": ["Closure OK", "Closure OK", "Bad Closure", "Closure OK", "Closure OK", "Closure OK"],
        "is_reject": [False, False, False, False, False, False],
    })


def test_success_rate_counts_all_closures():
    result = kpi.success_rate(_sample_closures())
    assert result["total_closures"] == 6
    assert result["successful"] == 6  # is_reject all False in this sample


def test_success_rate_per_head_returns_one_row_per_head():
    result = kpi.success_rate_per_head(_sample_closures())
    assert set(result["head_id"]) == {"H01", "H02"}


def test_torque_stats_returns_expected_keys():
    result = kpi.torque_stats(_sample_closures())
    assert "average_torque" in result
    assert result["count"] == 6


def test_detect_drift_returns_dataframe():
    result = trend.detect_drift(_sample_closures(), window=2, drift_threshold=0.01)
    assert isinstance(result, pd.DataFrame)


def test_zscore_anomalies_flags_outlier():
    result = anomaly.zscore_anomalies(_sample_closures(), threshold=1.5)
    assert len(result) >= 1
    assert 5.0 in result["app_torque"].values
