from pathlib import Path

import pandas as pd

from src.analytics import plots


def _sample_closures():
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=6, freq="min"),
        "head_id": ["H01", "H01", "H01", "H02", "H02", "H02"],
        "count": [1, 2, 3, 1, 2, 3],
        "app_torque": [2.5, 2.6, 2.4, 2.5, 2.5, 5.0],
        "status": [0, 0, 65, 0, 0, 0],
        "status_label": ["Closure OK", "Closure OK", "Bad Closure", "Closure OK", "Closure OK", "Closure OK"],
        "is_reject": [False, False, False, False, False, False],
    })


def test_plot_torque_over_time_saves_file(tmp_path):
    result = plots.plot_torque_over_time(_sample_closures(), output_dir=str(tmp_path))
    assert "file" in result
    assert Path(result["file"]).exists()
    assert result["points_available"] == 5  # excludes the one "Bad Closure" row


def test_plot_torque_over_time_single_head(tmp_path):
    result = plots.plot_torque_over_time(_sample_closures(), output_dir=str(tmp_path), head_id="H01")
    assert Path(result["file"]).exists()
    assert result["points_available"] == 2


def test_plot_torque_over_time_empty_data_returns_error(tmp_path):
    result = plots.plot_torque_over_time(_sample_closures(), output_dir=str(tmp_path), head_id="H99")
    assert "error" in result


def test_plot_torque_histogram_saves_file(tmp_path):
    result = plots.plot_torque_histogram(_sample_closures(), output_dir=str(tmp_path), bins=3)
    assert Path(result["file"]).exists()
    assert result["n"] == 5


def test_plot_success_rate_per_head_saves_file(tmp_path):
    result = plots.plot_success_rate_per_head(_sample_closures(), output_dir=str(tmp_path))
    assert Path(result["file"]).exists()
    assert result["heads_plotted"] == 2


def test_plot_failed_closures_over_time_saves_file(tmp_path):
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
    result = plots.plot_failed_closures_over_time(closures, output_dir=str(tmp_path), freq="D")
    assert Path(result["file"]).exists()
    assert result["periods"] == 2
    assert result["total_failed"] == 1


def test_plot_dashboard_summary_saves_file(tmp_path):
    result = plots.plot_dashboard_summary(_sample_closures(), output_dir=str(tmp_path))
    assert Path(result["file"]).exists()


def test_plot_functions_on_empty_dataframe_return_error(tmp_path):
    empty = _sample_closures().iloc[0:0]
    assert "error" in plots.plot_success_rate_per_head(empty, output_dir=str(tmp_path))
    assert "error" in plots.plot_failed_closures_over_time(empty, output_dir=str(tmp_path))
    assert "error" in plots.plot_dashboard_summary(empty, output_dir=str(tmp_path))
