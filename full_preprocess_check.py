import time
from pathlib import Path

import pandas as pd
import yaml

from src.ingestion.loader import list_data_files, load_raw_file
from src.ingestion.normalizer import (
    reshape_wide_to_long,
    validate,
    drop_duplicates,
)
from src.closure_detection.detector import (
    detect_closures,
    classify_status,
)
from src.ingestion import db


with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)


files = list_data_files(config)

print(f"Files found: {len(files)}")
print("Database:", config["database"]["path"])
print()


# Safety: don't accidentally append to an old full database.
db_path = Path(config["database"]["path"])
manifest_path = Path(config["database"]["manifest_path"])

if db_path.exists() or manifest_path.exists():
    print("Existing database or manifest found.")
    print("Delete/move them before doing a clean full rebuild.")
    raise SystemExit(1)


start_total = time.perf_counter()

previous_tail = None
first_batch = True


for number, path in enumerate(files, start=1):

    start_file = time.perf_counter()

    print(
        f"[{number}/{len(files)}] "
        f"Processing {path.name}"
    )

    # -------------------------------------------------
    # RAW TELEMETRY
    # -------------------------------------------------

    raw = load_raw_file(
        path,
        config,
    )

    db.save_raw_file(
        raw,
        config,
        replace_table=first_batch,
    )

    # -------------------------------------------------
    # NORMALIZATION
    # -------------------------------------------------

    long_df = reshape_wide_to_long(
        raw,
        config,
    )

    issues = validate(long_df)

    for issue in issues:
        print("  Validation:", issue)

    long_df = drop_duplicates(long_df)

    mode = "replace" if first_batch else "append"

    db.save_readings(
        long_df,
        config,
        mode=mode,
    )

    # -------------------------------------------------
    # CROSS-FILE CONTINUITY
    # -------------------------------------------------

    if previous_tail is not None:
        detection_df = pd.concat(
            [
                previous_tail,
                long_df,
            ],
            ignore_index=True,
        )
    else:
        detection_df = long_df

    # -------------------------------------------------
    # COUNTER-ADVANCE / CLOSURE RECORDS
    # -------------------------------------------------

    closures = detect_closures(
        detection_df,
    )

    closures = classify_status(
        closures,
        config["status_codes"],
    )

    db.save_closures(
        closures,
        config,
        mode=mode,
    )

    previous_tail = (
        long_df
        .sort_values(
            ["head_id", "timestamp"]
        )
        .groupby(
            "head_id",
            sort=False,
        )
        .tail(1)
        .copy()
    )

    file_time = time.perf_counter() - start_file

    print(
        f"  raw={len(raw):,} | "
        f"readings={len(long_df):,} | "
        f"closures={len(closures):,} | "
        f"{file_time:.1f}s"
    )

    first_batch = False

    del raw
    del long_df
    del detection_df
    del closures


# Only mark the pool as processed after every file succeeds.
db.update_manifest(config)

total_time = time.perf_counter() - start_total


# -----------------------------------------------------
# FINAL DATABASE VALIDATION
# -----------------------------------------------------

conn = db.get_connection(config)

raw_count = conn.execute(
    "SELECT COUNT(*) FROM raw_telemetry"
).fetchone()[0]

readings_count = 0

readings_dir = (
    Path(config["database"]["path"]).parent
    / "readings"
)

for parquet_file in readings_dir.glob("*.parquet"):
    readings_count += len(
        pd.read_parquet(
            parquet_file,
            columns=["timestamp"],
        )
    )

closures_count = conn.execute(
    "SELECT COUNT(*) FROM closures"
).fetchone()[0]

source_count = conn.execute(
    """
    SELECT COUNT(DISTINCT source_file)
    FROM raw_telemetry
    """
).fetchone()[0]

invalid_increments = conn.execute(
    """
    SELECT COUNT(*)
    FROM closures
    WHERE count_increment <= 0
    """
).fetchone()[0]

max_increment = conn.execute(
    """
    SELECT MAX(count_increment)
    FROM closures
    """
).fetchone()[0]

conn.close()


database_size_gb = (
    db_path.stat().st_size
    / 1024**3
)


print()
print("=" * 60)
print("FULL PREPROCESSING COMPLETE")
print("=" * 60)

print(
    "Source files:",
    source_count,
)

print(
    "Raw rows:",
    f"{raw_count:,}",
)

print(
    "Readings rows:",
    f"{readings_count:,}",
)

print(
    "Closure records:",
    f"{closures_count:,}",
)

print(
    "Invalid increments:",
    invalid_increments,
)

print(
    "Largest count increment:",
    max_increment,
)

print(
    "Database size:",
    round(database_size_gb, 2),
    "GB",
)

print(
    "Total processing time:",
    round(total_time / 60, 2),
    "minutes",
)

print(
    "Needs reprocessing:",
    db.needs_reprocessing(config),
)