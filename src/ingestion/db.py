"""
SQL persistence layer (SQLite), owned by Person A.

Three tables, in pipeline order:
    raw_telemetry  - wide format, untouched, appended as new files arrive
    readings       - long format, one row per (timestamp, head_id)
    closures       - one row per real closure event, with status_label/is_reject

Also implements the manifest-based freshness check so ingestion +
normalization + closure detection don't re-run on every app startup if the
raw data pool hasn't changed.
"""
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def get_connection(config: dict) -> sqlite3.Connection:
    db_path = Path(config["database"]["path"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


# --- manifest / freshness check -------------------------------------------

def _file_signature(path: Path) -> str:
    """Cheap fingerprint: size + modification time. Swap for a hash if you
    need to detect silently-edited files with preserved timestamps."""
    stat = path.stat()
    return f"{stat.st_size}-{stat.st_mtime}"


def _load_manifest(manifest_path: Path) -> dict:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {}


def needs_reprocessing(config: dict) -> bool:
    """True if any raw file is new or changed since the last recorded run,
    or if no cache exists yet."""
    folder = Path(config["data_pool"]["folder"])
    pattern = config["data_pool"]["file_pattern"]
    manifest_path = Path(config["database"]["manifest_path"])
    db_path = Path(config["database"]["path"])

    if not db_path.exists() or not manifest_path.exists():
        return True

    manifest = _load_manifest(manifest_path)

    files = list(folder.glob(pattern))

    if not files:
        logger.warning(
        "No raw files found in %s matching %s",
        folder,
        pattern,
    )
        return bool(manifest)

    current = {
        f.name: _file_signature(f)
        for f in files
    }

    return current != manifest


def update_manifest(config: dict) -> None:
    folder = Path(config["data_pool"]["folder"])
    pattern = config["data_pool"]["file_pattern"]
    manifest_path = Path(config["database"]["manifest_path"])

    manifest = {f.name: _file_signature(f) for f in folder.glob(pattern)}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))


# --- table read/write helpers ----------------------------------------------

def save_raw_telemetry(raw_df: pd.DataFrame, config: dict) -> None:
    """
    Changed files replace their previously stored rows.
    """
    folder = Path(config["data_pool"]["folder"])
    pattern = config["data_pool"]["file_pattern"]
    manifest_path = Path(config["database"]["manifest_path"])

    db_path = Path(config["database"]["path"])
    db_exists = db_path.exists()

    current_files = {
        f.name: _file_signature(f)
        for f in folder.glob(pattern)
    }

    old_manifest = _load_manifest(manifest_path)


    conn = get_connection(config)

    if not old_manifest or not db_exists:
        raw_df.to_sql(
            "raw_telemetry",
            conn,
            if_exists="replace",
            index=False,
        )
        conn.close()
        return

    changed_files = {
        name
        for name, signature in current_files.items()
        if old_manifest.get(name) != signature
    }

    removed_files = (
        set(old_manifest)
        - set(current_files)
    )

    for source_file in changed_files | removed_files:
        conn.execute(
            """
            DELETE FROM raw_telemetry
            WHERE source_file = ?
            """,
            (source_file,),
        )

    if changed_files:
        changed_rows = raw_df[
            raw_df["source_file"].isin(changed_files)
        ]

        changed_rows.to_sql(
            "raw_telemetry",
            conn,
            if_exists="append",
            index=False,
        )

    conn.commit()
    conn.close()


def save_readings(readings_df: pd.DataFrame, config: dict) -> None:
    """Derived table - always fully recomputed from raw_telemetry."""
    conn = get_connection(config)
    readings_df.to_sql("readings", conn, if_exists="replace", index=False)
    conn.close()


def load_readings(config: dict) -> pd.DataFrame:
    conn = get_connection(config)
    try:
        df = pd.read_sql("SELECT * FROM readings", conn, parse_dates=["timestamp"])
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    conn.close()
    return df


def save_closures(closures_df: pd.DataFrame, config: dict) -> None:
    """Derived table - always fully recomputed."""
    conn = get_connection(config)
    closures_df.to_sql("closures", conn, if_exists="replace", index=False)
    conn.close()


def load_closures(config: dict) -> pd.DataFrame:
    conn = get_connection(config)
    try:
        df = pd.read_sql("SELECT * FROM closures", conn, parse_dates=["timestamp"])
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    conn.close()
    return df
