"""
Loads raw telemetry data pool files (wide format, one row per second, one
Count/AppTorque/Status triplet per head) from the folder configured in
config.yaml. No hard-coded paths - everything comes from config.
"""

from pathlib import Path
import logging

import polars as pl


logger = logging.getLogger(__name__)


def list_data_files(config: dict) -> list[Path]:
    folder = Path(config["data_pool"]["folder"])
    pattern = config["data_pool"]["file_pattern"]

    files = sorted(folder.glob(pattern))

    if not files:
        logger.warning(
            "No data files found in %s matching %s",
            folder,
            pattern,
        )

    return files


def load_raw_file(
    path: Path,
    config: dict,
) -> pl.DataFrame:
    try:
        df = pl.read_csv(
            path,
            try_parse_dates=True,
        )
    except Exception as exc:
        logger.error(
            "Failed to load %s: %s",
            path,
            exc,
        )
        raise

    # Derive machine_id from filename convention:
    # telemetry_<machine_id>_<date>.csv
    #
    # Kept for provenance even though the
    # current dataset is single-machine.
    stem_parts = path.stem.split("_")

    machine_id = (
        stem_parts[1]
        if len(stem_parts) > 1
        else "unknown"
    )

    df = df.with_columns(
        pl.lit(machine_id).alias("machine_id"),
        pl.lit(path.name).alias("source_file"),
    )

    return df


def load_all(
    config: dict,
) -> pl.DataFrame:
    frames = [
        load_raw_file(path, config)
        for path in list_data_files(config)
    ]

    if not frames:
        return pl.DataFrame()

    return pl.concat(
        frames,
        how="vertical",
    )