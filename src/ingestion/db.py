"""
Persistence layer owned by Person A.

raw_telemetry -> SQLite
readings      -> ZSTD Parquet
closures      -> SQLite

A manifest prevents unnecessary reprocessing when the raw data pool
has not changed.
"""

import json
import logging
import sqlite3
from pathlib import Path

import adbc_driver_sqlite.dbapi as adbc_sqlite
import polars as pl


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Connections
# ------------------------------------------------------------------

def get_connection(config: dict) -> sqlite3.Connection:
    db_path = Path(config["database"]["path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _get_adbc_connection(config: dict):
    db_path = Path(config["database"]["path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return adbc_sqlite.connect(
        str(db_path.resolve())
    )


def _table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    result = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return result is not None


def _write_table(
    df: pl.DataFrame,
    table_name: str,
    config: dict,
    mode: str,
) -> None:
    if df.is_empty():
        return

    with _get_adbc_connection(config) as conn:
        df.write_database(
            table_name=table_name,
            connection=conn,
            if_table_exists=mode,
            engine="adbc",
        )
        conn.commit()


# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------

def _file_signature(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}-{stat.st_mtime}"


def _load_manifest(
    manifest_path: Path,
) -> dict:
    if manifest_path.exists():
        return json.loads(
            manifest_path.read_text()
        )

    return {}


def needs_reprocessing(
    config: dict,
) -> bool:
    folder = Path(
        config["data_pool"]["folder"]
    )

    pattern = config[
        "data_pool"
    ]["file_pattern"]

    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    db_path = Path(
        config["database"]["path"]
    )

    if (
        not db_path.exists()
        or not manifest_path.exists()
    ):
        return True

    manifest = _load_manifest(
        manifest_path
    )

    files = list(
        folder.glob(pattern)
    )

    if not files:
        logger.warning(
            "No raw files found in %s matching %s",
            folder,
            pattern,
        )
        return bool(manifest)

    current = {
        path.name: _file_signature(path)
        for path in files
    }

    return current != manifest


def update_manifest(
    config: dict,
) -> None:
    folder = Path(
        config["data_pool"]["folder"]
    )

    pattern = config[
        "data_pool"
    ]["file_pattern"]

    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    manifest = {
        path.name: _file_signature(path)
        for path in folder.glob(pattern)
    }

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
    )


def get_file_changes(
    config: dict,
) -> tuple[set[str], set[str]]:
    folder = Path(
        config["data_pool"]["folder"]
    )

    pattern = config[
        "data_pool"
    ]["file_pattern"]

    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    current = {
        path.name: _file_signature(path)
        for path in folder.glob(pattern)
    }

    manifest = _load_manifest(
        manifest_path
    )

    changed = {
        name
        for name, signature in current.items()
        if manifest.get(name) != signature
    }

    removed = (
        set(manifest)
        - set(current)
    )

    return changed, removed


# ------------------------------------------------------------------
# Raw telemetry
# ------------------------------------------------------------------

def save_raw_file(
    raw_df: pl.DataFrame,
    config: dict,
    replace_table: bool = False,
) -> None:

    if raw_df.is_empty():
        return

    source_files = (
        raw_df
        .get_column("source_file")
        .drop_nulls()
        .unique()
        .to_list()
    )

    if len(source_files) != 1:
        raise ValueError(
            "save_raw_file expects exactly one source file."
        )

    source_file = source_files[0]

    if replace_table:
        _write_table(
            raw_df,
            "raw_telemetry",
            config,
            "replace",
        )
        return

    conn = get_connection(config)

    table_exists = _table_exists(
        conn,
        "raw_telemetry",
    )

    if table_exists:
        conn.execute(
            """
            DELETE FROM raw_telemetry
            WHERE source_file = ?
            """,
            (source_file,),
        )

        conn.commit()

    conn.close()

    _write_table(
        raw_df,
        "raw_telemetry",
        config,
        "append" if table_exists else "replace",
    )


def delete_raw_sources(
    source_files: set[str],
    config: dict,
) -> None:

    if not source_files:
        return

    conn = get_connection(config)

    if _table_exists(
        conn,
        "raw_telemetry",
    ):
        conn.executemany(
            """
            DELETE FROM raw_telemetry
            WHERE source_file = ?
            """,
            [
                (name,)
                for name in source_files
            ],
        )

        conn.commit()

    conn.close()


def save_raw_telemetry(
    raw_df: pl.DataFrame,
    config: dict,
) -> None:
    """
    Incrementally synchronize raw telemetry.
    """

    folder = Path(
        config["data_pool"]["folder"]
    )

    pattern = config[
        "data_pool"
    ]["file_pattern"]

    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    db_path = Path(
        config["database"]["path"]
    )

    current_files = {
        path.name: _file_signature(path)
        for path in folder.glob(pattern)
    }

    old_manifest = _load_manifest(
        manifest_path
    )

    conn = get_connection(config)

    table_exists = _table_exists(
        conn,
        "raw_telemetry",
    )

    conn.close()

    if (
        not old_manifest
        or not db_path.exists()
        or not table_exists
    ):
        _write_table(
            raw_df,
            "raw_telemetry",
            config,
            "replace",
        )
        return

    changed = {
        name
        for name, signature
        in current_files.items()
        if old_manifest.get(name)
        != signature
    }

    removed = (
        set(old_manifest)
        - set(current_files)
    )

    conn = get_connection(config)

    for source_file in changed | removed:
        conn.execute(
            """
            DELETE FROM raw_telemetry
            WHERE source_file = ?
            """,
            (source_file,),
        )

    conn.commit()
    conn.close()

    if changed:
        changed_rows = raw_df.filter(
            pl.col("source_file")
            .is_in(list(changed))
        )

        _write_table(
            changed_rows,
            "raw_telemetry",
            config,
            "append",
        )


# ------------------------------------------------------------------
# Normalized readings
# ------------------------------------------------------------------

def save_readings(
    readings_df: pl.DataFrame,
    config: dict,
    mode: str = "replace",
) -> None:

    readings_dir = (
        Path(config["database"]["path"]).parent
        / "readings"
    )

    if (
        mode == "replace"
        and readings_dir.exists()
    ):
        for path in readings_dir.glob(
            "*.parquet"
        ):
            path.unlink()

    readings_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if readings_df.is_empty():
        return

    source_files = (
        readings_df
        .get_column("source_file")
        .drop_nulls()
        .unique()
        .to_list()
    )

    if len(source_files) != 1:
        raise ValueError(
            "save_readings expects exactly one source file."
        )

    output_path = (
        readings_dir
        / f"{Path(source_files[0]).stem}.parquet"
    )

    (
        readings_df
        .select(
            [
                "timestamp",
                "head_id",
                "count",
                "app_torque",
                "status",
            ]
        )
        .write_parquet(
            output_path,
            compression="zstd",
        )
    )


def load_readings(
    config: dict,
) -> pl.DataFrame:

    readings_dir = (
        Path(config["database"]["path"]).parent
        / "readings"
    )

    if not any(
        readings_dir.glob("*.parquet")
    ):
        return pl.DataFrame()

    return (
        pl.scan_parquet(
            str(
                readings_dir
                / "*.parquet"
            )
        )
        .collect()
    )


# ------------------------------------------------------------------
# Closures
# ------------------------------------------------------------------

def save_closures(
    closures_df: pl.DataFrame,
    config: dict,
    mode: str = "replace",
) -> None:

    _write_table(
        closures_df,
        "closures",
        config,
        mode,
    )


def load_closures(
    config: dict,
) -> pl.DataFrame:

    db_path = Path(
        config["database"]["path"]
    )

    if not db_path.exists():
        return pl.DataFrame()

    conn = get_connection(config)

    exists = _table_exists(
        conn,
        "closures",
    )

    conn.close()

    if not exists:
        return pl.DataFrame()

    with _get_adbc_connection(config) as conn:
        return pl.read_database(
            query="SELECT * FROM closures",
            connection=conn,
        )