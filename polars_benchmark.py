import time
from pathlib import Path

import pandas as pd
import polars as pl
import yaml

from src.ingestion.loader import list_data_files, load_raw_file
from src.ingestion.normalizer import (
    reshape_wide_to_long,
    drop_duplicates,
)
from src.closure_detection.detector import (
    detect_closures,
    classify_status,
)


with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)


# ------------------------------------------------------------
# Use first 10 real files
# ------------------------------------------------------------

files = list_data_files(config)[:10]

print(f"Benchmarking {len(files)} files")
print()


benchmark_dir = Path(
    "data/.cache/benchmark_polars_large"
)

benchmark_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# Clean old benchmark output
for path in benchmark_dir.glob("*.parquet"):
    path.unlink()


# ============================================================
# TOTALS
# ============================================================

pandas_load = 0
pandas_normalize = 0
pandas_detect = 0
pandas_write = 0

polars_load = 0
polars_normalize = 0
polars_detect = 0
polars_write = 0

pandas_readings = 0
polars_readings = 0

pandas_closures = 0
polars_closures = 0

pandas_max_increment = 0
polars_max_increment = 0

pandas_total_start = time.perf_counter()


# ============================================================
# PANDAS
# ============================================================

print("PANDAS")
print("-" * 60)

for number, path in enumerate(files, start=1):

    print(
        f"[{number}/{len(files)}] {path.name}"
    )

    # Load
    start = time.perf_counter()

    raw = load_raw_file(
        path,
        config,
    )

    pandas_load += (
        time.perf_counter() - start
    )

    # Normalize
    start = time.perf_counter()

    long_df = reshape_wide_to_long(
        raw,
        config,
    )

    long_df = drop_duplicates(
        long_df,
    )

    pandas_normalize += (
        time.perf_counter() - start
    )

    # Detect
    start = time.perf_counter()

    closures = detect_closures(
        long_df,
    )

    closures = classify_status(
        closures,
        config["status_codes"],
    )

    pandas_detect += (
        time.perf_counter() - start
    )

    # Compact readings
    compact = long_df[
        [
            "timestamp",
            "head_id",
            "count",
            "app_torque",
            "status",
        ]
    ].copy()

    compact["count"] = compact[
        "count"
    ].astype("int64")

    compact["status"] = compact[
        "status"
    ].astype("int64")

    # Write benchmark parquet
    output = (
        benchmark_dir
        / f"pandas_{number:02d}.parquet"
    )

    start = time.perf_counter()

    compact.to_parquet(
        output,
        engine="pyarrow",
        compression="zstd",
        index=False,
    )

    pandas_write += (
        time.perf_counter() - start
    )

    pandas_readings += len(long_df)
    pandas_closures += len(closures)

    if len(closures):
        pandas_max_increment = max(
            pandas_max_increment,
            closures["count_increment"].max(),
        )

    del raw
    del long_df
    del compact
    del closures


pandas_total = (
    time.perf_counter()
    - pandas_total_start
)


# ============================================================
# POLARS
# ============================================================

print()
print("POLARS")
print("-" * 60)

polars_total_start = time.perf_counter()


count_suffix = config["schema"]["count_suffix"]
torque_suffix = config["schema"]["torque_suffix"]
status_suffix = config["schema"]["status_suffix"]
timestamp_col = config["schema"]["timestamp_column"]


status_labels = {
    int(code): details["label"]
    for code, details
    in config["status_codes"].items()
}

status_rejects = {
    int(code): details["reject"]
    for code, details
    in config["status_codes"].items()
}


for number, path in enumerate(files, start=1):

    print(
        f"[{number}/{len(files)}] {path.name}"
    )

    # Load
    start = time.perf_counter()

    raw = pl.read_csv(
        path,
        try_parse_dates=True,
    )

    machine_id = (
        path.stem.split("_")[1]
    )

    raw = raw.with_columns(
        pl.lit(machine_id).alias(
            "machine_id"
        ),
        pl.lit(path.name).alias(
            "source_file"
        ),
    )

    polars_load += (
        time.perf_counter() - start
    )

    # Normalize
    start = time.perf_counter()

    heads = sorted(
        column[:-len(count_suffix)]
        for column in raw.columns
        if column.endswith(count_suffix)
    )

    head_frames = []

    for head in heads:

        frame = raw.select(
            pl.col(timestamp_col).alias(
                "timestamp"
            ),

            pl.col("machine_id"),

            pl.lit(head).alias(
                "head_id"
            ),

            pl.col(
                f"{head}{count_suffix}"
            )
            .cast(pl.Int64)
            .alias("count"),

            pl.col(
                f"{head}{torque_suffix}"
            )
            .cast(pl.Float64)
            .alias("app_torque"),

            pl.col(
                f"{head}{status_suffix}"
            )
            .cast(pl.Int64)
            .alias("status"),

            pl.col("source_file"),
        )

        head_frames.append(frame)

    long_df = pl.concat(
        head_frames,
        how="vertical",
    )

    long_df = long_df.unique(
        maintain_order=True,
    )

    polars_normalize += (
        time.perf_counter() - start
    )

    # Detect
    start = time.perf_counter()

    working = (
        long_df
        .sort(
            [
                "head_id",
                "timestamp",
            ]
        )
        .with_columns(
            pl.col("count")
            .shift(1)
            .over("head_id")
            .alias("count_prev"),

            pl.col("timestamp")
            .diff()
            .over("head_id")
            .dt.total_seconds()
            .alias(
                "time_since_prev_seconds"
            ),
        )
        .with_columns(
            (
                pl.col("count")
                - pl.col("count_prev")
            ).alias(
                "count_increment"
            )
        )
    )

    closures = (
        working
        .filter(
            (pl.col("count_increment") > 0)
            & (pl.col("count") > 0)
            & (pl.col("count_prev") > 0)
        )
        .select(
            [
                "timestamp",
                "head_id",
                "count",
                "count_increment",
                "time_since_prev_seconds",
                "app_torque",
                "status",
            ]
        )
        .with_columns(
            pl.col("status")
            .replace_strict(
                status_labels,
                default="Unknown",
            )
            .alias("status_label"),

            pl.col("status")
            .replace_strict(
                status_rejects,
                default=False,
            )
            .alias("is_reject"),
        )
    )

    polars_detect += (
        time.perf_counter() - start
    )

    # Compact readings
    compact = long_df.select(
        [
            "timestamp",
            "head_id",
            "count",
            "app_torque",
            "status",
        ]
    )

    output = (
        benchmark_dir
        / f"polars_{number:02d}.parquet"
    )

    start = time.perf_counter()

    compact.write_parquet(
        output,
        compression="zstd",
    )

    polars_write += (
        time.perf_counter() - start
    )

    polars_readings += long_df.height
    polars_closures += closures.height

    if closures.height:
        current_max = (
            closures
            .select(
                pl.col(
                    "count_increment"
                ).max()
            )
            .item()
        )

        polars_max_increment = max(
            polars_max_increment,
            current_max,
        )

    del raw
    del long_df
    del working
    del compact
    del closures


polars_total = (
    time.perf_counter()
    - polars_total_start
)


# ============================================================
# STORAGE
# ============================================================

pandas_size = sum(
    path.stat().st_size
    for path
    in benchmark_dir.glob(
        "pandas_*.parquet"
    )
) / 1024**2


polars_size = sum(
    path.stat().st_size
    for path
    in benchmark_dir.glob(
        "polars_*.parquet"
    )
) / 1024**2


# ============================================================
# RESULTS
# ============================================================

print()
print("=" * 60)
print("10-FILE PANDAS VS POLARS")
print("=" * 60)

print()
print("PANDAS")
print("Load:", round(pandas_load, 2), "s")
print("Normalize:", round(pandas_normalize, 2), "s")
print("Detect:", round(pandas_detect, 2), "s")
print("Parquet write:", round(pandas_write, 2), "s")
print("TOTAL:", round(pandas_total, 2), "s")

print()
print("POLARS")
print("Load:", round(polars_load, 2), "s")
print("Normalize:", round(polars_normalize, 2), "s")
print("Detect:", round(polars_detect, 2), "s")
print("Parquet write:", round(polars_write, 2), "s")
print("TOTAL:", round(polars_total, 2), "s")

print()
print("CORRECTNESS")

print(
    "Pandas readings:",
    f"{pandas_readings:,}",
)

print(
    "Polars readings:",
    f"{polars_readings:,}",
)

print(
    "Pandas closures:",
    f"{pandas_closures:,}",
)

print(
    "Polars closures:",
    f"{polars_closures:,}",
)

print(
    "Pandas max increment:",
    pandas_max_increment,
)

print(
    "Polars max increment:",
    polars_max_increment,
)

print()
print("PARQUET SIZE")

print(
    "Pandas:",
    round(pandas_size, 2),
    "MB",
)

print(
    "Polars:",
    round(polars_size, 2),
    "MB",
)

print()
print("SPEEDUP")

print(
    round(
        pandas_total / polars_total,
        2,
    ),
    "x",
)