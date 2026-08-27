"""
Chart-generation functions on classified closure events. Each function
renders a matplotlib figure, saves it as a PNG under `output_dir`, and
returns a small dict describing the artifact (file path + a few summary
numbers) - never the image itself, since the LLM orchestrator only ever
sees text/JSON tool results. The actual PNG is what the user opens.

Same contract as the rest of analytics/: first argument is the `closures`
DataFrame, plus simple keyword arguments; restricted to status_label ==
"Closure OK" wherever torque values are involved - see kpi.py's module
note on why "not is_reject" alone would pull stats toward the zero-torque
"No Load" rows.
"""
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_MAX_LEGEND_HEADS = 12
_MAX_SCATTER_POINTS = 5000


def _save_and_close(fig, output_dir: str, name: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _downsample(df: pd.DataFrame, max_points: int = _MAX_SCATTER_POINTS) -> pd.DataFrame:
    """Evenly-spaced subsample so large datasets stay fast/legible to plot.
    Assumes df is already sorted the way the caller wants points spread."""
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step]


def plot_torque_over_time(closures: pd.DataFrame, output_dir: str, head_id: str = None,
                           start_date: str = None, end_date: str = None) -> dict:
    """Line/scatter plot of applied torque over time for successful closures,
    optionally restricted to one head and/or a date range; saves a PNG and
    returns its path."""
    data = closures[closures["status_label"] == "Closure OK"]
    if head_id is not None:
        data = data[data["head_id"] == head_id]
    if start_date is not None:
        data = data[data["timestamp"] >= start_date]
    if end_date is not None:
        data = data[data["timestamp"] <= end_date]

    if data.empty:
        return {"error": "No successful closures to plot for the given filter."}

    data = data.sort_values("timestamp")
    fig, ax = plt.subplots(figsize=(10, 4))

    period_str = ""
    if start_date or end_date:
        period_str = f" ({start_date or '...'} to {end_date or '...'})"

    if head_id is not None:
        plotted = _downsample(data)
        ax.plot(plotted["timestamp"], plotted["app_torque"], marker=".", markersize=2, linestyle="")
        title = f"Torque over time - {head_id}{period_str}"
    else:
        heads = data["head_id"].unique()
        plotted = _downsample(data)
        show_legend = len(heads) <= _MAX_LEGEND_HEADS
        for hid, group in plotted.groupby("head_id"):
            ax.plot(
                group["timestamp"], group["app_torque"],
                marker=".", markersize=2, linestyle="", alpha=0.5,
                label=hid if show_legend else None,
            )
        if show_legend:
            ax.legend(loc="upper right", fontsize="small", ncol=2)
        title = f"Torque over time - all heads{period_str}"

    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Applied torque (Nm)")
    ax.set_title(title)
    fig.autofmt_xdate()

    path = _save_and_close(fig, output_dir, "torque_over_time")
    return {
        "file": path,
        "chart_type": "scatter",
        "title": title,
        "points_plotted": int(len(plotted)),
        "points_available": int(len(data)),
    }

def plot_torque_histogram(closures: pd.DataFrame, output_dir: str, bins: int = 20, successful_only: bool = True) -> dict:
    """Histogram of applied torque values; saves a PNG and returns its path."""
    data = closures[closures["status_label"] == "Closure OK"] if successful_only else closures

    if data.empty:
        return {"error": "No closures to plot for the given filter."}

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(data["app_torque"], bins=bins, color="#4C72B0", edgecolor="white")
    ax.set_xlabel("Applied torque (Nm)")
    ax.set_ylabel("Count")
    title = "Torque distribution" + (" (successful closures)" if successful_only else " (all closures)")
    ax.set_title(title)

    path = _save_and_close(fig, output_dir, "torque_histogram")
    return {"file": path, "chart_type": "histogram", "title": title, "n": int(len(data))}


def plot_success_rate_per_head(closures: pd.DataFrame, output_dir: str) -> dict:
    """Bar chart of success rate per head, sorted worst to best; saves a PNG
    and returns its path."""
    if closures.empty:
        return {"error": "No closures to plot."}

    grouped = closures.groupby("head_id").agg(total=("is_reject", "count"), failed=("is_reject", "sum"))
    grouped["success_rate_pct"] = 100 * (grouped["total"] - grouped["failed"]) / grouped["total"]
    grouped = grouped.sort_values("success_rate_pct")

    fig, ax = plt.subplots(figsize=(max(6, len(grouped) * 0.3), 4))
    ax.bar(grouped.index.astype(str), grouped["success_rate_pct"], color="#55A868")
    ax.set_xlabel("Head")
    ax.set_ylabel("Success rate (%)")
    ax.set_title("Success rate per head")
    ax.set_ylim(0, 100)
    plt.setp(ax.get_xticklabels(), rotation=90 if len(grouped) > 15 else 0)

    path = _save_and_close(fig, output_dir, "success_rate_per_head")
    return {
        "file": path,
        "chart_type": "bar",
        "title": "Success rate per head",
        "heads_plotted": int(len(grouped)),
        "lowest_head": str(grouped.index[0]),
        "lowest_success_rate_pct": round(float(grouped["success_rate_pct"].iloc[0]), 2),
    }


def plot_failed_closures_over_time(closures: pd.DataFrame, output_dir: str, freq: str = "D") -> dict:
    """Bar chart of failed closure counts over time (default daily buckets);
    saves a PNG and returns its path."""
    if closures.empty:
        return {"error": "No closures to plot."}

    df = closures.copy()
    df["period"] = df["timestamp"].dt.floor(freq)
    grouped = df.groupby("period")["is_reject"].sum()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(grouped.index, grouped.values, color="#C44E52")
    ax.set_xlabel("Time")
    ax.set_ylabel("Failed closures")
    ax.set_title("Failed closures over time")
    fig.autofmt_xdate()

    path = _save_and_close(fig, output_dir, "failed_closures_over_time")
    return {
        "file": path,
        "chart_type": "bar",
        "title": "Failed closures over time",
        "periods": int(len(grouped)),
        "total_failed": int(grouped.sum()),
    }


def plot_dashboard_summary(closures: pd.DataFrame, output_dir: str) -> dict:
    """Combined dashboard (success rate per head, torque histogram, torque
    over time, failed closures per day) as one PNG; saves it and returns
    its path."""
    if closures.empty:
        return {"error": "No closures to plot."}

    ok = closures[closures["status_label"] == "Closure OK"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    grouped = closures.groupby("head_id").agg(total=("is_reject", "count"), failed=("is_reject", "sum"))
    grouped["success_rate_pct"] = 100 * (grouped["total"] - grouped["failed"]) / grouped["total"]
    grouped = grouped.sort_values("success_rate_pct")
    axes[0, 0].bar(grouped.index.astype(str), grouped["success_rate_pct"], color="#55A868")
    axes[0, 0].set_title("Success rate per head")
    axes[0, 0].set_ylim(0, 100)
    plt.setp(axes[0, 0].get_xticklabels(), rotation=90 if len(grouped) > 15 else 0)

    if not ok.empty:
        axes[0, 1].hist(ok["app_torque"], bins=20, color="#4C72B0", edgecolor="white")
    axes[0, 1].set_title("Torque distribution (successful closures)")

    if not ok.empty:
        sample = _downsample(ok.sort_values("timestamp"))
        axes[1, 0].plot(sample["timestamp"], sample["app_torque"], marker=".", markersize=1, linestyle="", alpha=0.3, color="#4C72B0")
    axes[1, 0].set_title("Torque over time (successful closures)")
    plt.setp(axes[1, 0].get_xticklabels(), rotation=30)

    df = closures.copy()
    df["period"] = df["timestamp"].dt.floor("D")
    failed_grouped = df.groupby("period")["is_reject"].sum()
    axes[1, 1].bar(failed_grouped.index, failed_grouped.values, color="#C44E52")
    axes[1, 1].set_title("Failed closures per day")
    plt.setp(axes[1, 1].get_xticklabels(), rotation=30)

    fig.suptitle("Capping process dashboard summary")
    fig.tight_layout()

    path = _save_and_close(fig, output_dir, "dashboard_summary")
    return {"file": path, "chart_type": "dashboard", "title": "Capping process dashboard summary"}


def plot_failures_per_head(closures: pd.DataFrame, output_dir: str,
                             start_date: str = None, end_date: str = None) -> dict:
    """Bar chart of raw failure count per head, sorted worst to best,
    optionally restricted to a date range; saves a PNG and returns its path."""
    data = closures
    if start_date is not None:
        data = data[data["timestamp"] >= start_date]
    if end_date is not None:
        data = data[data["timestamp"] <= end_date]

    if data.empty:
        return {"error": "No closures to plot for the given filter."}

    grouped = data.groupby("head_id")["is_reject"].sum().sort_values(ascending=False)

    period_str = f" ({start_date or '...'} to {end_date or '...'})" if (start_date or end_date) else ""

    fig, ax = plt.subplots(figsize=(max(6, len(grouped) * 0.3), 4))
    ax.bar(grouped.index.astype(str), grouped.values, color="#C44E52")
    ax.set_xlabel("Head")
    ax.set_ylabel("Failed closures (count)")
    ax.set_title(f"Failed closures per head{period_str}")
    plt.setp(ax.get_xticklabels(), rotation=90 if len(grouped) > 15 else 0)

    path = _save_and_close(fig, output_dir, "failures_per_head")
    return {
        "file": path,
        "chart_type": "bar",
        "title": f"Failed closures per head{period_str}",
        "heads_plotted": int(len(grouped)),
        "highest_head": str(grouped.index[0]),
        "highest_failure_count": int(grouped.iloc[0]),
    }