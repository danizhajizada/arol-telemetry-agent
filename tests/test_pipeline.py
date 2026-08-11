import pandas as pd

import src.cli as cli
from src.ingestion import db


def test_prepare_closures_end_to_end_and_uses_cache(tmp_path, monkeypatch):

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = tmp_path / "telemetry.db"
    manifest_path = tmp_path / "manifest.json"

    config = {
        "data_pool": {
            "folder": str(data_dir),
            "file_pattern": "telemetry_*.csv",
        },
        "database": {
            "path": str(db_path),
            "manifest_path": str(manifest_path),
        },
        "schema": {
            "timestamp_column": "timestamp",
            "count_suffix": " Count",
            "torque_suffix": " AppTorque",
            "status_suffix": " Status",
        },
        "status_codes": {
            0: {
                "label": "Closure OK",
                "reject": False,
            },
            2: {
                "label": "No Load",
                "reject": False,
            },
            65: {
                "label": "Bad Closure (reject)",
                "reject": True,
            },
        },
    }

    #Creating a new file

    source_file = data_dir / "telemetry_M1.csv"

    source_df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01 00:00:00",
            "2026-01-01 00:00:01",
            "2026-01-01 00:00:02",
            "2026-01-01 00:00:03",
            "2026-01-01 00:00:04",
        ]),
        "H01 Count": [
            100,
            100,
            101,
            101,
            102,
        ],
        "H01 AppTorque": [
            0.0,
            0.0,
            2.01,
            2.00,
            1.88,
        ],
        "H01 Status": [
            2,
            2,
            0,
            0,
            65,
        ],
    })

    source_df.to_csv(source_file, index=False)


    closures = cli._prepare_closures(config)

    # Counter changes:
    # 100 -> 100 = nothing
    # 100 -> 101 = closure/counter advance
    # 101 -> 101 = nothing
    # 101 -> 102 = closure/counter advance

    assert len(closures) == 2

    assert list(closures["count"]) == [101, 102]

    assert list(closures["count_increment"]) == [1, 1]

    assert list(closures["status_label"]) == [
        "Closure OK",
        "Bad Closure (reject)",
    ]

    assert list(closures["is_reject"]) == [
        False,
        True,
    ]


    conn = db.get_connection(config)

    raw_count = pd.read_sql(
        "SELECT COUNT(*) AS n FROM raw_telemetry",
        conn,
    ).iloc[0]["n"]

    readings_count = pd.read_sql(
        "SELECT COUNT(*) AS n FROM readings",
        conn,
    ).iloc[0]["n"]

    closures_count = pd.read_sql(
        "SELECT COUNT(*) AS n FROM closures",
        conn,
    ).iloc[0]["n"]

    conn.close()

    # 5 original telemetry timestamps
    assert raw_count == 5

    # 5 timestamps x 1 head
    assert readings_count == 5

    # Two positive counter advances
    assert closures_count == 2

    # Manifest must have been created after successful processing.
    assert manifest_path.exists()

    assert not db.needs_reprocessing(config)


    def fail_if_loader_runs(*args, **kwargs):
        raise AssertionError(
            "load_all() was called even though the data pool "
            "has not changed."
        )

    monkeypatch.setattr(
        cli,
        "load_all",
        fail_if_loader_runs,
    )

    cached_closures = cli._prepare_closures(config)

    assert len(cached_closures) == 2

    assert list(cached_closures["count"]) == [101, 102]

    # Database must remain unchanged.
    conn = db.get_connection(config)

    raw_count_after = pd.read_sql(
        "SELECT COUNT(*) AS n FROM raw_telemetry",
        conn,
    ).iloc[0]["n"]

    closures_count_after = pd.read_sql(
        "SELECT COUNT(*) AS n FROM closures",
        conn,
    ).iloc[0]["n"]

    conn.close()

    assert raw_count_after == 5
    assert closures_count_after == 2