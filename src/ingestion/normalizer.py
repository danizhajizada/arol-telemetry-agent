"""
Normalizes raw wide-format telemetry into a long-format internal schema:
    timestamp, head_id, count, app_torque, status
Also runs basic validation (missing values, duplicates, counter sanity).
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _find_head_ids(columns: list[str], count_suffix: str) -> list[str]:
    heads = []
    for col in columns:
        if col.endswith(count_suffix):
            heads.append(col[: -len(count_suffix)])
    return heads


def reshape_wide_to_long(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    schema = config["schema"]
    ts_col = schema["timestamp_column"]
    count_suf = schema["count_suffix"]
    torque_suf = schema["torque_suffix"]
    status_suf = schema["status_suffix"]

    head_ids = _find_head_ids(df.columns.tolist(), count_suf)
    if not head_ids:
        raise ValueError("No head columns found - check schema suffixes in config.")

    long_frames = []
    for head_id in head_ids:
        cols = {
            f"{head_id}{count_suf}": "count",
            f"{head_id}{torque_suf}": "app_torque",
            f"{head_id}{status_suf}": "status",
        }
        missing = [c for c in cols if c not in df.columns]
        if missing:
            logger.warning("Head %s missing columns %s - skipping", head_id, missing)
            continue

        sub = df[[ts_col, "machine_id", "source_file"] + list(cols.keys())].copy()
        sub = sub.rename(columns=cols)
        sub["head_id"] = head_id
        long_frames.append(sub)

    long_df = pd.concat(long_frames, ignore_index=True)
    long_df = long_df.rename(columns={ts_col: "timestamp"})
    return long_df[
        ["timestamp", "machine_id", "head_id", "count", "app_torque", "status", "source_file"]
    ]


def validate(long_df: pd.DataFrame) -> list[str]:
    issues = []
    if long_df.empty:
        issues.append("Dataset is empty after reshaping.")
        return issues

    missing_counts = long_df[["count", "app_torque", "status"]].isna().sum()
    for col, n in missing_counts.items():
        if n > 0:
            issues.append(f"{n} missing values in '{col}'.")

    dupes = long_df.duplicated(subset=["timestamp", "head_id"]).sum()
    if dupes > 0:
        issues.append(f"{dupes} duplicate (timestamp, head_id) rows found.")

    for head_id, group in long_df.groupby("head_id"):
        sorted_group = group.sort_values("timestamp")
        if (sorted_group["count"].diff().dropna() < 0).any():
            issues.append(f"Counter decreased for head {head_id}.")

    return issues


def drop_duplicates(long_df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate (timestamp, head_id) rows - true duplicates,
    not idle noise, which is filtered later during closure detection."""
    return long_df.drop_duplicates(subset=["timestamp", "head_id"]).reset_index(drop=True)
