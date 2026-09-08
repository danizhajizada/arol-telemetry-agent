"""
CLI entry point.

python -m src.cli ask "What is the average closing torque for successful closures?"
python -m src.cli report kpi
python -m src.cli report anomalies
python -m src.cli report drift
python -m src.cli chat
"""
import time
import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import logging

import polars as pl
import typer
import yaml


from src.agent.orchestrator import run_agent, AgentResult
from src.reporting.report_builder import save_text_report
from src.agent import tools as agent_tools

from src.ingestion.pipeline import prepare_closures

app = typer.Typer(help="AROL telemetry agent CLI")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CANNED_REQUESTS = {
    "kpi": (
        "Generate an overall KPI report: "
        "success rate, torque stats, and capping speed."
    ),
    "anomalies": (
        "Generate an anomaly report: "
        "flag unusual torque values."
    ),
    "drift": (
        "Generate a trend report: "
        "identify any heads showing torque drift."
    ),
}


def _load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)




def _run_agent(
    question: str,
    closures: pl.DataFrame,
    config: dict,
) -> AgentResult:
    """
    Preserve the existing Person B/C pandas interface.
    """
    df = closures.to_pandas()
    df["is_reject"] = df["is_reject"].astype(bool)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    del closures
    return run_agent(
        question,
        df,
        config,
    )


@app.command()
def ask(
    question: str,
    pool: str = "config/config.yaml",
):
    """Ask a free-text question about the telemetry data."""

    config = _load_config(pool)

    t0 = time.time()
    closures = prepare_closures(config)
    agent_tools.set_readings_config(config)
    t1 = time.time()
    typer.echo(f"[TIMING] Load closures: {t1 - t0:.2f}s ({len(closures)} rows)")

    result = _run_agent(question, closures, config)
    t2 = time.time()
    typer.echo(f"[TIMING] Agent total: {t2 - t1:.2f}s")

    typer.echo(result.text)
    if result.generated_files:
        typer.echo("\nGenerated charts:")
        for file_path in result.generated_files:
            typer.echo(f"  - {file_path}")
    reports_dir = config.get("output", {}).get("reports_dir", "output/reports/")
    saved_path = save_text_report("ask", question, result.text, result.generated_files, reports_dir)
    typer.echo(f"\n[SAVED] Report written to {saved_path}")
    
@app.command()
def report(
    kind: str,
    pool: str = "config/config.yaml",
):
    """Generate a canned KPI, anomaly, or drift report and save it to disk."""

    if kind not in CANNED_REQUESTS:
        typer.echo(
            f"Unknown report kind '{kind}'. "
            f"Choose from: {list(CANNED_REQUESTS)}"
        )
        raise typer.Exit(code=1)

    config = _load_config(pool)

    t0 = time.time()
    closures = prepare_closures(config)
    agent_tools.set_readings_config(config)
    t1 = time.time()
    typer.echo(f"[TIMING] Load closures: {t1 - t0:.2f}s ({len(closures)} rows)")

    question = CANNED_REQUESTS[kind]
    result = _run_agent(question, closures, config)
    t2 = time.time()
    typer.echo(f"[TIMING] Agent total: {t2 - t1:.2f}s")

    typer.echo(result.text)

    reports_dir = config.get("output", {}).get("reports_dir", "output/reports/")
    saved_path = save_text_report(kind, question, result.text, result.generated_files, reports_dir)
    typer.echo(f"\n[SAVED] Report written to {saved_path}")


@app.command()
def chat(pool: str = "config/config.yaml"):
    """Interactive question loop against the real telemetry data. Type 'exit' or 'quit' to stop."""
    config = _load_config(pool)

    t0 = time.time()
    closures_pl = prepare_closures(config)
    agent_tools.set_readings_config(config)
    t1 = time.time()
    typer.echo(f"[TIMING] Load closures: {t1 - t0:.2f}s ({len(closures_pl)} rows)")

    t_convert = time.time()
    closures = closures_pl.to_pandas()
    closures["is_reject"] = closures["is_reject"].astype(bool)
    closures["timestamp"] = pd.to_datetime(closures["timestamp"])
    typer.echo(f"[TIMING] Convert to pandas: {time.time() - t_convert:.2f}s")

    typer.echo("AROL telemetry agent - interactive mode (real data)")
    typer.echo("Type a question, or 'exit' to quit.\n")

    while True:
        question = typer.prompt("You")
        if question.strip().lower() in {"exit", "quit"}:
            typer.echo("Goodbye.")
            break

        q_start = time.time()
        result = run_agent(question, closures, config)   # <- call run_agent directly, not _run_agent
        typer.echo(f"[TIMING] Agent total: {time.time() - q_start:.2f}s")
        typer.echo(f"\n{result.text}\n")
        if result.generated_files:
            typer.echo("Generated charts:")
            for file_path in result.generated_files:
                typer.echo(f"  - {file_path}")
            typer.echo("")


if __name__ == "__main__":
    app()