import polars as pl

from src.closure_detection.detector import (
    detect_closures,
    classify_status,
    detect_idle_periods,
)


def _sample_long_df():
    return (
        pl.DataFrame({
            "timestamp": [
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:01",
                "2026-01-01T00:00:02",
                "2026-01-01T00:00:03",
            ],
            "head_id": ["H01"] * 4,
            "count": [100, 100, 100, 101],
            "app_torque": [2.5, 2.5, 2.5, 2.6],
            "status": [0, 0, 0, 0],
        })
        .with_columns(
            pl.col("timestamp").str.to_datetime()
        )
    )


def test_detect_closures_only_flags_count_change():
    closures = detect_closures(
        _sample_long_df()
    )

    assert closures.height == 1

    event = closures.row(
        0,
        named=True,
    )

    assert event["count"] == 101
    assert event["app_torque"] == 2.6


def test_classify_status_maps_reject_flag():
    closures = detect_closures(
        _sample_long_df()
    )

    status_codes = {
        0: {
            "label": "Closure OK",
            "reject": False,
        }
    }

    classified = classify_status(
        closures,
        status_codes,
    )

    event = classified.row(
        0,
        named=True,
    )

    assert event["status_label"] == "Closure OK"
    assert not event["is_reject"]


def test_detect_idle_periods_requires_sustained_duration():
    df = (
        _sample_long_df()
        .with_columns(
            pl.lit(2).alias("status")
        )
    )

    idle_long_threshold = detect_idle_periods(
        df,
        idle_status_code=2,
        sustained_seconds=10,
    )

    assert idle_long_threshold.is_empty()

    idle_short_threshold = detect_idle_periods(
        df,
        idle_status_code=2,
        sustained_seconds=2,
    )

    assert idle_short_threshold.height == 1


def test_detect_closures_ignores_zero_counter_dropouts():
    df = (
        pl.DataFrame({
            "timestamp": [
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:01",
                "2026-01-01T00:00:02",
                "2026-01-01T00:00:03",
                "2026-01-01T00:00:04",
            ],
            "head_id": ["H01"] * 5,
            "count": [100, 100, 0, 100, 101],
            "app_torque": [
                2.5,
                2.5,
                0.0,
                2.5,
                2.6,
            ],
            "status": [0, 0, 0, 0, 0],
        })
        .with_columns(
            pl.col("timestamp").str.to_datetime()
        )
    )

    closures = detect_closures(df)

    assert closures.height == 1

    event = closures.row(
        0,
        named=True,
    )

    assert event["count"] == 101


def test_idle_detection_breaks_on_timestamp_gap():
    df = (
        pl.DataFrame({
            "timestamp": [
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:01",
                "2026-01-01 00:10:00",
                "2026-01-01 00:10:01",
            ],
            "head_id": ["H01"] * 4,
            "status": [2, 2, 2, 2],
        })
        .with_columns(
            pl.col("timestamp").str.to_datetime()
        )
    )

    idle_periods = detect_idle_periods(
        df,
        idle_status_code=2,
        sustained_seconds=300,
    )

    assert idle_periods.is_empty()


def test_idle_detection_respects_gap_tolerance():
    df = (
        pl.DataFrame({
            "timestamp": [
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:02",
                "2026-01-01 00:10:00",
                "2026-01-01 00:10:02",
            ],
            "head_id": ["H01"] * 4,
            "status": [2, 2, 2, 2],
        })
        .with_columns(
            pl.col("timestamp").str.to_datetime()
        )
    )

    idle_periods = detect_idle_periods(
        df,
        idle_status_code=2,
        sustained_seconds=300,
        max_gap_seconds=2,
    )

    assert idle_periods.is_empty()


def test_detect_closures_preserves_counter_increment():
    df = (
        pl.DataFrame({
            "timestamp": [
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:01",
                "2026-01-01 00:00:02",
            ],
            "head_id": ["H01"] * 3,
            "count": [100, 100, 103],
            "app_torque": [2.0, 2.0, 2.1],
            "status": [0, 0, 0],
        })
        .with_columns(
            pl.col("timestamp").str.to_datetime()
        )
    )

    closures = detect_closures(df)

    assert closures.height == 1

    event = closures.row(
        0,
        named=True,
    )

    assert event["count"] == 103
    assert event["count_increment"] == 3
    assert event["time_since_prev_seconds"] == 1