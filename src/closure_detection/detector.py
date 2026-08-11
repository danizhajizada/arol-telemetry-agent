"""
Detects positive counter advances, classifies their status,
and identifies sustained idle periods.
"""

import polars as pl


def detect_closures(long_df: pl.DataFrame) -> pl.DataFrame:
    df = (
        long_df
        .sort(["head_id", "timestamp"])
        .with_columns(
            pl.col("count")
            .shift(1)
            .over("head_id")
            .alias("count_prev"),

            pl.col("timestamp")
            .diff()
            .over("head_id")
            .dt.total_seconds()
            .alias("time_since_prev_seconds"),
        )
        .with_columns(
            (
                pl.col("count") - pl.col("count_prev")
            ).alias("count_increment")
        )
    )

    return (
        df
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
    )


def classify_status(
    closures: pl.DataFrame,
    status_codes: dict,
) -> pl.DataFrame:

    labels = {
        int(code): values["label"]
        for code, values in status_codes.items()
    }

    rejects = {
        int(code): values["reject"]
        for code, values in status_codes.items()
    }

    unknown_label = pl.concat_str(
        [
            pl.lit("Unknown ("),
            pl.col("status").cast(pl.String),
            pl.lit(")"),
        ]
    )

    return closures.with_columns(
        pl.col("status")
        .replace_strict(
            labels,
            default=unknown_label,
            return_dtype=pl.String,
        )
        .alias("status_label"),

        pl.col("status")
        .replace_strict(
            rejects,
            default=False,
            return_dtype=pl.Boolean,
        )
        .alias("is_reject"),
    )


def detect_idle_periods(
    long_df: pl.DataFrame,
    idle_status_code: int,
    sustained_seconds: int,
    max_gap_seconds: int = 2,
) -> pl.DataFrame:

    df = (
        long_df
        .sort(["head_id", "timestamp"])
        .with_columns(
            (pl.col("status") == idle_status_code)
            .alias("is_idle"),

            (
                pl.col("timestamp")
                .diff()
                .over("head_id")
                > pl.duration(seconds=max_gap_seconds)
            ).alias("time_gap"),
        )
        .with_columns(
            (
                (
                    pl.col("is_idle")
                    != pl.col("is_idle")
                    .shift(1)
                    .over("head_id")
                )
                | pl.col("time_gap")
            )
            .fill_null(True)
            .cast(pl.Int64)
            .cum_sum()
            .over("head_id")
            .alias("run_id")
        )
    )

    return (
        df
        .filter(pl.col("is_idle"))
        .group_by(["head_id", "run_id"])
        .agg(
            pl.col("timestamp").min().alias("start"),
            pl.col("timestamp").max().alias("end"),
            pl.len().alias("n_rows"),
        )
        .with_columns(
            (
                pl.col("end") - pl.col("start")
            )
            .dt.total_seconds()
            .alias("duration_seconds")
        )
        .filter(
            pl.col("duration_seconds")
            >= sustained_seconds
        )
        .drop("run_id")
        .sort(["head_id", "start"])
    )