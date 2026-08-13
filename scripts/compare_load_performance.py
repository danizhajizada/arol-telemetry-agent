"""
Compares load performance between the SQLite-backed `closures` table and
the Parquet-backed `readings` table, normalized by row count, to get a
fair "time per million rows" comparison - evidence for whether switching
`closures` to Parquet (matching `readings`) would help.
"""
import time
import yaml

from src.ingestion import db

config = yaml.safe_load(open("config/config.yaml"))


def timed_load(label: str, load_fn):
    print(f"Loading {label}...")
    t0 = time.time()
    result = load_fn()
    elapsed = time.time() - t0
    rows = result.height  # Polars DataFrame
    rows_per_sec = rows / elapsed if elapsed > 0 else float("inf")
    ms_per_million_rows = (elapsed / rows * 1_000_000 * 1000) if rows > 0 else 0

    print(f"  Rows:                 {rows:,}")
    print(f"  Time:                 {elapsed:.2f}s")
    print(f"  Rows/sec:             {rows_per_sec:,.0f}")
    print(f"  Time per 1M rows:     {ms_per_million_rows:.0f} ms")
    print()
    return elapsed, rows


closures_time, closures_rows = timed_load(
    "closures (SQLite via ADBC)",
    lambda: db.load_closures(config),
)

readings_time, readings_rows = timed_load(
    "readings (Parquet, ZSTD)",
    lambda: db.load_readings(config),
)

print("=" * 50)
print("SUMMARY")
print("=" * 50)

closures_ms_per_million = (closures_time / closures_rows * 1_000_000 * 1000) if closures_rows > 0 else 0
readings_ms_per_million = (readings_time / readings_rows * 1_000_000 * 1000) if readings_rows > 0 else 0

print(f"closures (SQLite):  {closures_ms_per_million:.0f} ms per 1M rows")
print(f"readings (Parquet): {readings_ms_per_million:.0f} ms per 1M rows")

if readings_ms_per_million > 0:
    ratio = closures_ms_per_million / readings_ms_per_million
    print(f"\nSQLite is {ratio:.1f}x slower than Parquet, per row.")