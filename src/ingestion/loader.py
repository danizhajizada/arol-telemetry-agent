"""
Loads raw telemetry data pool files (wide format, one row per second, one
Count/AppTorque/Status triplet per head) from the folder configured in
config.yaml. No hard-coded paths - everything comes from config.
"""
from pathlib import Path
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def list_data_files(config: dict) -> list[Path]:
    folder = Path(config["data_pool"]["folder"])
    pattern = config["data_pool"]["file_pattern"]
    files = sorted(folder.glob(pattern))
    if not files:
        logger.warning("No data files found in %s matching %s", folder, pattern)
    return files


def load_raw_file(path: Path, config: dict) -> pd.DataFrame:
    ts_col = config["schema"]["timestamp_column"]
    try:
        df = pd.read_csv(path, parse_dates=[ts_col])
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        raise

    # Derive machine_id from filename convention: telemetry_<machine_id>_<date>.csv
    # (kept for provenance even though the current dataset is single-machine)
    stem_parts = path.stem.split("_")
    machine_id = stem_parts[1] if len(stem_parts) > 1 else "unknown"
    df["machine_id"] = machine_id
    df["source_file"] = path.name
    return df


def load_all(config: dict) -> pd.DataFrame:
    frames = [load_raw_file(f, config) for f in list_data_files(config)]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
