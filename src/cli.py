"""
CLI entry point.

    python -m src.cli ask "What is the average closing torque for successful closures?"
    python -m src.cli report kpi
    python -m src.cli report anomalies
    python -m src.cli report drift
"""
import logging

import typer
import yaml

from pathlib import Path
import pandas as pd

from src.ingestion.loader import list_data_files, load_raw_file
from src.ingestion.normalizer import reshape_wide_to_long, validate, drop_duplicates
from src.ingestion import db
from src.closure_detection.detector import detect_closures, classify_status
from src.agent.orchestrator import run_agent

app = typer.Typer(help="AROL telemetry agent CLI")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CANNED_REQUESTS = {
    "kpi": "Generate an overall KPI report: success rate, torque stats, and capping speed.",
    "anomalies": "Generate an anomaly report: flag unusual torque values.",
    "drift": "Generate a trend report: identify any heads showing torque drift.",
}


def _load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def _prepare_closures(config: dict):
    """Prepare closure data using file-by-file processing.
    Processing one source file at a time avoids constructing the complete
    long-format telemetry dataset in memory.
    """
    # Use cache when nothing is changed
    if not db.needs_reprocessing(config):
        cached = db.load_closures(config)

        if not cached.empty:
            logger.info(
                "Using cached closures table "
                "(no new/changed raw files)."
            )
            return cached

    logger.info(
        "Raw data pool changed or no cache found - "
        "running file-by-file pipeline."
    )

    files = list_data_files(config)

    if not files:
        typer.echo(
            "No data found - check config data_pool.folder."
        )
        raise typer.Exit(code=1)

    
    # Changed files
    db_path = Path(config["database"]["path"])
    manifest_path = Path(
        config["database"]["manifest_path"]
    )

    full_raw_rebuild = (
        not db_path.exists()
        or not manifest_path.exists()
    )

    changed_files, removed_files = db.get_file_changes(
        config
    )

    # If the database/manifest does not yet exist,
    # every current file needs to be stored.
    if full_raw_rebuild:
        changed_files = {
            path.name
            for path in files
        }

    # Remove raw rows belonging to files that disappeared.
    db.delete_raw_sources(
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

        # Raw table only changes for new/modified files.
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

        long_df = drop_duplicates(long_df)

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
            detection_df = pd.concat(
                [
                    previous_tail,
                    long_df,
                ],
                ignore_index=True,
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
            mode=mode,
        )

        # Preserve only 36 rows:
        # the final reading for each head.
        previous_tail = (
            long_df
            .sort_values(
                [
                    "head_id",
                    "timestamp",
                ]
            )
            .groupby(
                "head_id",
                sort=False,
            )
            .tail(1)
            .copy()
        )

        first_batch = False

        # Allow this file's large dataframes to be
        # reclaimed before processing the next file.
        del raw
        del long_df
        del detection_df
        del closures

    db.update_manifest(config)

    return db.load_closures(config)


@app.command()
def ask(question: str, pool: str = "config/config.yaml"):
    """Ask a free-text question about the telemetry data."""
    config = _load_config(pool)
    closures = _prepare_closures(config)
    typer.echo(run_agent(question, closures, config))


@app.command()
def report(kind: str, pool: str = "config/config.yaml"):
    """Generate a canned report. KIND is one of: kpi, anomalies, drift."""
    if kind not in CANNED_REQUESTS:
        typer.echo(f"Unknown report kind '{kind}'. Choose from: {list(CANNED_REQUESTS)}")
        raise typer.Exit(code=1)

    config = _load_config(pool)
    closures = _prepare_closures(config)
    typer.echo(run_agent(CANNED_REQUESTS[kind], closures, config))


if __name__ == "__main__":
    app()
