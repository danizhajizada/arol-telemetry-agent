"""
End-to-end telemetry preparation pipeline owned by Person A.

This module handles:
- raw CSV discovery
- incremental raw persistence
- normalization
- validation
- duplicate cleaning
- readings persistence
- closure/counter-advance reconstruction
- status classification
- manifest updates

The CLI should only call prepare_closures().
"""

import logging
from pathlib import Path

import polars as pl

from src.ingestion.loader import (
    list_data_files,
    load_raw_file,
)
from src.ingestion.normalizer import (
    reshape_wide_to_long,
    validate,
    drop_duplicates,
)
from src.ingestion import db
from src.closure_detection.detector import (
    detect_closures,
    classify_status,
)


logger = logging.getLogger(__name__)


def prepare_closures(
    config: dict,
) -> pl.DataFrame:
    """
    Prepare closure/counter-advance data from the configured
    telemetry pool.

    Cached derived data is reused when the source files have
    not changed.

    Processing is performed one source file at a time to keep
    memory usage bounded.
    """

    if not db.needs_reprocessing(config):
        cached = db.load_closures(config)

        if not cached.is_empty():
            logger.info(
                "Using cached closures "
                "(no new/changed raw files)."
            )
            return cached

    logger.info(
        "Raw data pool changed or no cache found - "
        "running file-by-file pipeline."
    )

    files = list_data_files(config)

    if not files:
        raise FileNotFoundError(
            "No telemetry files found. "
            "Check data_pool.folder and file_pattern."
        )

    db_path = Path(
        config["database"]["path"]
    )

    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    full_raw_rebuild = (
        not db_path.exists()
        or not manifest_path.exists()
    )

    changed_files, removed_files = (
        db.get_file_changes(config)
    )

    if full_raw_rebuild:
        changed_files = {
            path.name
            for path in files
        }

    db.delete_raw_sources(
        removed_files,
        config,
    )

    db.delete_closure_sources(
    removed_files,
    config,
    )

    previous_tail = None
    first_batch = True
    first_raw_write = True

    for path in files:
        logger.info(
            "Processing %s",
            path.name,
        )

        raw = load_raw_file(
            path,
            config,
        )

        if path.name in changed_files:
            db.save_raw_file(
                raw,
                config,
                replace_table=(
                    full_raw_rebuild
                    and first_raw_write
                ),
            )

            first_raw_write = False

        long_df = reshape_wide_to_long(
            raw,
            config,
        )

        for issue in validate(long_df):
            logger.warning(
                "Validation issue in %s: %s",
                path.name,
                issue,
            )

        long_df = drop_duplicates(
            long_df
        )

        mode = (
            "replace"
            if first_batch
            else "append"
        )

        db.save_readings(
            long_df,
            config,
            mode=mode,
        )

        if previous_tail is not None:
            detection_df = pl.concat(
                [
                    previous_tail,
                    long_df,
                ],
                how="vertical",
            )
        else:
            detection_df = long_df

        closures = detect_closures(
            detection_df
        )

        closures = classify_status(
            closures,
            config["status_codes"],
        )

        db.save_closures(
            closures,
            config,
            source_file=path.name,
            mode=mode,
        )

        previous_tail = (
            long_df
            .sort(
                [
                    "head_id",
                    "timestamp",
                ]
            )
            .unique(
                subset=["head_id"],
                keep="last",
                maintain_order=True,
            )
        )

        first_batch = False

        del raw
        del long_df
        del detection_df
        del closures

    db.update_manifest(config)

    return db.load_closures(config)