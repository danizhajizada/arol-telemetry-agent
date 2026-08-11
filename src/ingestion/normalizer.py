"""
Normalizes raw wide-format telemetry into a long-format internal schema:
timestamp, head_id, count, app_torque, status

Also runs basic validation:
missing values, duplicates, and counter sanity.
"""

import logging

import polars as pl


logger = logging.getLogger(__name__)


def _find_head_ids(
    columns: list[str],
    count_suffix: str,
) -> list[str]:
    heads = []

    for col in columns:
        if col.endswith(count_suffix):
            heads.append(
                col[:-len(count_suffix)]
            )

    return heads


def reshape_wide_to_long(
    df: pl.DataFrame,
    config: dict,
) -> pl.DataFrame:

    schema = config["schema"]

    ts_col = schema["timestamp_column"]
    count_suf = schema["count_suffix"]
    torque_suf = schema["torque_suffix"]
    status_suf = schema["status_suffix"]

    head_ids = _find_head_ids(
        df.columns,
        count_suf,
    )

    if not head_ids:
        raise ValueError(
            "No head columns found - "
            "check schema suffixes in config."
        )

    # Keep only heads that have all three
    # telemetry columns.
    valid_heads = []

    for head_id in head_ids:

        required = [
            f"{head_id}{count_suf}",
            f"{head_id}{torque_suf}",
            f"{head_id}{status_suf}",
        ]

        missing = [
            col
            for col in required
            if col not in df.columns
        ]

        if missing:
            logger.warning(
                "Head %s missing columns %s - skipping",
                head_id,
                missing,
            )
            continue

        valid_heads.append(head_id)

    if not valid_heads:
        raise ValueError(
            "No complete head telemetry triplets found."
        )

    # Build one list per telemetry row containing
    # values for all valid heads, then explode those
    # lists together into long format.
    long_df = (
        df
        .select(
            pl.col(ts_col).alias("timestamp"),

            pl.col("machine_id"),

            pl.concat_list(
                [
                    pl.lit(head_id)
                    for head_id in valid_heads
                ]
            ).alias("head_id"),

            pl.concat_list(
                [
                    pl.col(
                        f"{head_id}{count_suf}"
                    )
                    for head_id in valid_heads
                ]
            ).alias("count"),

            pl.concat_list(
                [
                    pl.col(
                        f"{head_id}{torque_suf}"
                    )
                    for head_id in valid_heads
                ]
            ).alias("app_torque"),

            pl.concat_list(
                [
                    pl.col(
                        f"{head_id}{status_suf}"
                    )
                    for head_id in valid_heads
                ]
            ).alias("status"),

            pl.col("source_file"),
        )
            .explode(
        [
            "head_id",
            "count",
            "app_torque",
            "status",
        ],
        empty_as_null=True,
    )
        .with_columns(
            pl.col("count").cast(pl.Int64),
            pl.col("app_torque").cast(pl.Float64),
            pl.col("status").cast(pl.Int64),
        )
        .select(
            [
                "timestamp",
                "machine_id",
                "head_id",
                "count",
                "app_torque",
                "status",
                "source_file",
            ]
        )
    )

    return long_df


def validate(
    long_df: pl.DataFrame,
) -> list[str]:

    issues = []

    if long_df.is_empty():
        issues.append(
            "Dataset is empty after reshaping."
        )
        return issues

    # -------------------------------------------------
    # Missing values
    # -------------------------------------------------

    for col in [
        "count",
        "app_torque",
        "status",
    ]:

        missing_expr = (
            pl.col(col).is_null()
        )

        # pandas isna() also treated NaN as missing.
        # Preserve that behaviour for floating-point
        # telemetry.
        if long_df.schema[col] in (
            pl.Float32,
            pl.Float64,
        ):
            missing_expr = (
                missing_expr
                | pl.col(col).is_nan()
            )

        n = (
            long_df
            .select(
                missing_expr
                .sum()
                .alias("missing")
            )
            .item()
        )

        if n > 0:
            issues.append(
                f"{n} missing values in '{col}'."
            )

    # -------------------------------------------------
    # Duplicate timestamp/head records
    # -------------------------------------------------

    key_rows = long_df.select(
        [
            "timestamp",
            "head_id",
        ]
    )

    unique_key_rows = key_rows.unique()

    dupes = (
        key_rows.height
        - unique_key_rows.height
    )

    if dupes > 0:
        issues.append(
            f"{dupes} duplicate "
            "(timestamp, head_id) rows found."
        )

    # -------------------------------------------------
    # Counter sanity
    # -------------------------------------------------

    decreased_heads = (
        long_df
        .sort(
            [
                "head_id",
                "timestamp",
            ]
        )
        .with_columns(
            pl.col("count")
            .diff()
            .over("head_id")
            .alias("_count_diff")
        )
        .filter(
            pl.col("_count_diff") < 0
        )
        .select("head_id")
        .unique()
        .get_column("head_id")
        .to_list()
    )

    for head_id in sorted(decreased_heads):
        issues.append(
            f"Counter decreased for head {head_id}."
        )

    return issues


def drop_duplicates(
    long_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Remove duplicate (timestamp, head_id) rows.

    These are true duplicate records, not idle/no-load
    telemetry, which is handled later during closure
    detection.
    """

    return long_df.unique(
        subset=[
            "timestamp",
            "head_id",
        ],
        keep="first",
        maintain_order=True,
    )