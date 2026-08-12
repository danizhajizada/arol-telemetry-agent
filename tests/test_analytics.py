import pandas as pd
from src.analytics import kpi, trend, anomaly, correlation


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


def test_success_rate_over_time_groups_by_day():
    closures = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01 08:00", "2026-01-01 09:00",
            "2026-01-02 08:00", "2026-01-02 09:00",
        ]),
        "head_id": ["H01", "H01", "H01", "H01"],
        "count": [1, 2, 3, 4],
        "app_torque": [2.5, 2.5, 2.5, 2.5],
        "status": [0, 65, 0, 0],
        "status_label": ["Closure OK", "Bad Closure", "Closure OK", "Closure OK"],
        "is_reject": [False, True, False, False],
    })
    result = kpi.success_rate_over_time(closures, freq="D")
    assert len(result) == 2
    assert set(result.columns) >= {"period", "total_closures", "successful", "failed", "success_rate_pct"}
    day1 = result[result["period"] == pd.Timestamp("2026-01-01")].iloc[0]
    assert day1["total_closures"] == 2
    assert day1["failed"] == 1


def test_torque_distribution_returns_bins_covering_all_rows():
    result = kpi.torque_distribution(_sample_closures(), bins=3)
    assert "count" in result.columns
    assert result["count"].sum() == len(_sample_closures())


def test_torque_distribution_empty_when_no_successful_closures():
    all_rejected = _sample_closures().assign(is_reject=True)
    result = kpi.torque_distribution(all_rejected, successful_only=True)
    assert result.empty


def test_head_torque_correlation_returns_symmetric_matrix():
    result = correlation.head_torque_correlation(_sample_closures())
    assert result.shape == (2, 2)
    assert result.loc["H01", "H01"] == 1.0
    assert result.loc["H02", "H01"] == result.loc["H01", "H02"]
