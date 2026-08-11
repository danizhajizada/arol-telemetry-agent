import pandas as pd

from src.ingestion import db


def test_raw_telemetry_incremental_sync(tmp_path):
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
    }


    file_a = data_dir / "telemetry_A.csv"
    file_b = data_dir / "telemetry_B.csv"

    file_a.write_text("dummy A")
    file_b.write_text("dummy B")

    raw = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01 00:00:00",
            "2026-01-01 00:00:01",
            "2026-01-01 00:00:02",
            "2026-01-01 00:00:03",
        ]),
        "value": [10, 11, 20, 21],
        "source_file": [
            "telemetry_A.csv",
            "telemetry_A.csv",
            "telemetry_B.csv",
            "telemetry_B.csv",
        ],
    })

    assert db.needs_reprocessing(config)

    db.save_raw_telemetry(raw, config)
    db.update_manifest(config)

    conn = db.get_connection(config)
    stored = pd.read_sql(
        "SELECT * FROM raw_telemetry",
        conn,
    )
    conn.close()

    assert len(stored) == 4


    assert not db.needs_reprocessing(config)

    # Database must still contain exactly 4 rows.
    conn = db.get_connection(config)
    stored = pd.read_sql(
        "SELECT * FROM raw_telemetry",
        conn,
    )
    conn.close()

    assert len(stored) == 4

    # Adding a new file testing
    file_c = data_dir / "telemetry_C.csv"
    file_c.write_text("dummy C")

    assert db.needs_reprocessing(config)

    raw_with_c = pd.concat(
        [
            raw,
            pd.DataFrame({
                "timestamp": pd.to_datetime([
                    "2026-01-01 00:00:04",
                    "2026-01-01 00:00:05",
                ]),
                "value": [30, 31],
                "source_file": [
                    "telemetry_C.csv",
                    "telemetry_C.csv",
                ],
            }),
        ],
        ignore_index=True,
    )

    db.save_raw_telemetry(raw_with_c, config)
    db.update_manifest(config)

    conn = db.get_connection(config)
    stored = pd.read_sql(
        "SELECT * FROM raw_telemetry",
        conn,
    )
    conn.close()

    # A=2, B=2, C=2
    assert len(stored) == 6

   
    file_b.write_text("dummy B changed content")

    assert db.needs_reprocessing(config)

    raw_changed_b = raw_with_c.copy()

    # Simulate the changed contents of B.
    raw_changed_b.loc[
        raw_changed_b["source_file"] == "telemetry_B.csv",
        "value",
    ] = [200, 201]

    db.save_raw_telemetry(raw_changed_b, config)
    db.update_manifest(config)

    conn = db.get_connection(config)

    stored = pd.read_sql(
        "SELECT * FROM raw_telemetry",
        conn,
    )

    stored_b = pd.read_sql(
        """
        SELECT *
        FROM raw_telemetry
        WHERE source_file = 'telemetry_B.csv'
        """,
        conn,
    )

    conn.close()

    # Still 6 total rows — B was replaced, not duplicated.
    assert len(stored) == 6

    assert len(stored_b) == 2
    assert set(stored_b["value"]) == {200, 201}
    
    assert not db.needs_reprocessing(config)