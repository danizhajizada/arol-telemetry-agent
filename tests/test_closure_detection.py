import pandas as pd
from src.closure_detection.detector import detect_closures, classify_status, detect_idle_periods


def _sample_long_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01T00:00:00", "2026-01-01T00:00:01",
            "2026-01-01T00:00:02", "2026-01-01T00:00:03",
        ]),
        "head_id": ["H01"] * 4,
        "count": [100, 100, 100, 101],
        "app_torque": [2.5, 2.5, 2.5, 2.6],
        "status": [0, 0, 0, 0],
    })


def test_detect_closures_only_flags_count_change():
    closures = detect_closures(_sample_long_df())
    assert len(closures) == 1
    assert closures.iloc[0]["count"] == 101
    assert closures.iloc[0]["app_torque"] == 2.6


def test_classify_status_maps_reject_flag():
    closures = detect_closures(_sample_long_df())
    status_codes = {0: {"label": "Closure OK", "reject": False}}
    classified = classify_status(closures, status_codes)
    assert classified.iloc[0]["status_label"] == "Closure OK"
    assert classified.iloc[0]["is_reject"] is False


def test_detect_idle_periods_requires_sustained_duration():
    df = _sample_long_df()
    df["status"] = 2  # No Load for all 4 seconds
    idle_long_threshold = detect_idle_periods(df, idle_status_code=2, sustained_seconds=10)
    assert idle_long_threshold.empty  # only 3 seconds long, below threshold

    idle_short_threshold = detect_idle_periods(df, idle_status_code=2, sustained_seconds=2)
    assert len(idle_short_threshold) == 1
