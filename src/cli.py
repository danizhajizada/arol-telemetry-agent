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

from src.ingestion.loader import load_all
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
    """Runs the full ingestion -> normalization -> closure detection
    pipeline once, or loads the cached result if the raw data pool hasn't
    changed since the last run (see ingestion/db.py for the freshness
    check). This is the "load once, hold in memory" step - every question
    asked afterwards reuses the returned dataframe."""
    if not db.needs_reprocessing(config):
        cached = db.load_closures(config)
        if not cached.empty:
            logger.info("Using cached closures table (no new/changed raw files).")
            return cached

    logger.info("Raw data pool changed or no cache found - running full pipeline.")
    raw = load_all(config)
    if raw.empty:
        typer.echo("No data found - check config data_pool.folder.")
        raise typer.Exit(code=1)
    db.save_raw_telemetry(raw, config)

    long_df = reshape_wide_to_long(raw, config)
    for issue in validate(long_df):
        logger.warning("Validation issue: %s", issue)
    long_df = drop_duplicates(long_df)
    db.save_readings(long_df, config)

    closures = detect_closures(long_df)
    closures = classify_status(closures, config["status_codes"])
    db.save_closures(closures, config)

    db.update_manifest(config)
    return closures


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
