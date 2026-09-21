# Analytics Methods

This document describes `src/analytics/` — the deterministic function
library that sits between the `closures`/`readings` tables (see
`data_schema.md`) and the LLM agent (see `Agent_decision_flow.md`). Every
function here is ordinary, testable Python/Polars code; none of them call
the LLM, and none of them are non-deterministic - see `architecture.md`
for how this fits into the rest of the pipeline.

## Contract

Every function in this layer follows the same shape:

- Takes `closures` (a pandas `DataFrame`) as its first argument, plus a
  small number of optional keyword arguments (a head ID, a date range, a
  window size, a threshold) - never a database connection or a raw file
  path.
- Returns a small `dict` or a short `DataFrame`/list of records (at most a
  few dozen rows) - never the full input back. This matters because the
  agent layer forwards whatever a function returns directly to the LLM as
  tool-result JSON; returning millions of rows would be both too slow and
  unusable as context.
- Has a one-line docstring describing the question it answers in plain
  English, since the agent's tool descriptions (`src/agent/tools.py`) lean
  on this almost verbatim.

Two functions break the first rule by necessity - `idle_time_per_head` and
`machine_idle_periods_summary` in `kpi.py` - see "Idle-time analysis"
below for why, and how they stay consistent with everything else.

## The `closures` table: why torque functions filter further than `is_reject`

`data_schema.md` already defines `is_reject` and `status_label`; this
section covers how analytics specifically uses them, since getting it
wrong silently produces wrong numbers rather than a crash.

A row in `closures` is any counted head cycle, not necessarily a
successful bottle closure. Three kinds of rows exist side by side:

| Row type | `is_reject` | `app_torque` | Share of real dataset |
|---|---|---|---|
| **Closure OK** | `False` | real reading (~2 Nm) | majority |
| **No Load** (head cycled, no cap present) | `False` | ~0.0 | ~40-43% |
| **Reject** (Slow Torque, Bad Closure, etc.) | `True` | real reading | rare (~0.002%) |

Two different filters answer two different questions, and mixing them up
produces numbers that look plausible but aren't:

- **`is_reject == False`** answers "was this a confirmed failure?" - used
  by every `success_rate*` function. Under this definition, No Load counts
  as "successful" (it isn't a rejected cycle), which is a known, debated
  point - see "Open questions" below.
- **`status_label == "Closure OK"`** answers "was this a genuine capping
  cycle with a meaningful torque reading?" - used by every function that
  touches `app_torque` (`torque_stats`, `torque_distribution`,
  `moving_average`, `detect_drift`, `zscore_anomalies`,
  `head_torque_correlation`, and the torque-related plots). Filtering only
  on `is_reject` here would leave ~40% near-zero No Load rows in the
  population, which:
  - pulls every torque average/min/std toward zero,
  - makes the per-head torque distribution bimodal (~0 Nm and ~2 Nm
    clusters), which breaks the z-score threshold's assumption of a
    roughly unimodal distribution in `zscore_anomalies`,
  - makes a rolling average track the *changing mix* of No Load vs.
    Closure OK cycles rather than real torque drift, in `moving_average`
    and `detect_drift`,
  - makes two heads that happen to idle at the same time look strongly
    correlated in `head_torque_correlation`, from shared idle periods
    rather than a real mechanical relationship.

This distinction was found through direct investigation of an
unexpectedly low torque average during development, and every function
below states which filter it uses and why in its own docstring.

## Function reference

### `kpi.py` — headline numbers

| Function | Returns | Notes |
|---|---|---|
| `success_rate(closures)` | `dict`: total/successful/failed/success_rate_pct | `is_reject == False` definition of success |
| `success_rate_per_head(closures)` | `DataFrame`, one row per head | Same definition, broken out by head |
| `success_rate_over_time(closures, freq="D", head_id=None)` | `DataFrame` indexed by time bucket | `freq` is any pandas offset alias (`"D"`, `"h"`); optional single-head filter for spotting whether one head's failures cluster in time |
| `torque_stats(closures, successful_only=True)` | `dict`: count/mean/min/max/std | `successful_only` uses `status_label == "Closure OK"` |
| `torque_stats_per_head(closures, successful_only=True, head_id=None)` | `dict` (one head) or `list[dict]` (all heads) | Same filter semantics as `torque_stats` |
| `torque_distribution(closures, bins=10, successful_only=True)` | `DataFrame` histogram (`bin_start`, `bin_end`, `count`) | Same filter semantics |
| `capping_speed_incremental(closures)` | `DataFrame`: running pieces/hour per head | See below |
| `idle_time_per_head(config, sustained_seconds=300)` | `dict` keyed by head | Reads `readings` directly, not `closures` - see "Idle-time analysis" |
| `machine_idle_periods_summary(config, sustained_seconds=300)` | `list[dict]` | Same |

`capping_speed_incremental` sums `count_increment` (the real counter
advance from closure detection), not row count, because a single row can
represent several physical cycles at once - the counter can jump by more
than 1 between two observed telemetry rows, most often across a
timestamp gap, and closure detection does not fabricate the missing
intermediate cycles. Counting rows instead would understate throughput
whenever that happens. The first row of each head has zero elapsed time
by construction, so its speed is `NaN`.

### `trend.py` — moving average & drift

- **`moving_average(closures, window)`** → `DataFrame` with a rolling mean
  of `app_torque` per head over `window` *closures* (not wall-clock time -
  timestamp gaps of up to several hours can occur between consecutive rows
  for the same head, so a window should be read as "the last N observed
  closures," not "the last N minutes").
- **`detect_drift(closures, window=50, drift_threshold=0.1)`** → `DataFrame`,
  one row per head whose rolling-average torque changed by at least
  `drift_threshold` (fractional) between the start and end of the observed
  period.

Both restrict to `status_label == "Closure OK"` first (see above).

### `anomaly.py` — statistical outliers

**`zscore_anomalies(closures, threshold=3.0, limit=50)`** → `DataFrame` of
the closures whose torque is `threshold` or more standard deviations from
that head's mean, most extreme first. Restricted to `status_label ==
"Closure OK"` before computing the z-score, for the bimodal-distribution
reason explained above. `limit` (clamped to 1-500) caps how many rows come
back, since on the real dataset the number of closures past a low
threshold can run into the thousands - far more than an LLM tool result
should carry.

### `correlation.py` — cross-head relationships

**`head_torque_correlation(closures)`** → `DataFrame`, pairwise Pearson
correlation matrix of `app_torque` across heads. Rows are aligned by
*closure order* (`cumcount()` per head) rather than timestamp, since
different heads close at different rates and don't share a common time
grid. Restricted to `status_label == "Closure OK"` first.

### `plots.py` — chart generation

Same contract as the rest of the layer, with one difference: instead of
returning data, each function renders a matplotlib figure, saves it as a
PNG under `output_dir` (from `config.yaml`'s `output.plots_dir`), and
returns a small `dict` describing the artifact - file path plus a few
summary numbers - never the image itself, since the LLM only ever sees
text/JSON.

| Function | Chart | Notes |
|---|---|---|
| `plot_torque_over_time(closures, output_dir, head_id=None, start_date=None, end_date=None)` | scatter | All heads overlaid if `head_id` omitted |
| `plot_torque_histogram(closures, output_dir, bins=20, successful_only=True)` | histogram | |
| `plot_success_rate_per_head(closures, output_dir)` | bar, sorted worst-to-best | |
| `plot_failed_closures_over_time(closures, output_dir, freq="D")` | bar | |
| `plot_failures_per_head(closures, output_dir, start_date=None, end_date=None)` | bar, sorted worst-to-best | Raw failure counts, not rates |
| `plot_dashboard_summary(closures, output_dir)` | 2x2 combined figure | Success rate, torque histogram, torque-over-time, failures/day in one PNG |

Two safeguards keep plots readable and fast on the full dataset rather
than just on small samples:

- **Point downsampling** (`_downsample`, capped at 5,000 points): scatter
  plots evenly subsample rather than plotting every point, since the real
  dataset has tens of millions of rows per head over time.
- **Legend capping** (`_MAX_LEGEND_HEADS = 12`): a per-head legend is only
  drawn when there are 12 or fewer heads on the plot; beyond that a legend
  would just be unreadable clutter, so it's omitted instead.

## Idle-time analysis: a different data source, by necessity

`idle_time_per_head` and `machine_idle_periods_summary` (in `kpi.py`) are
the two functions in this layer that don't take `closures` as their first
argument - they take `config` instead, and read from `readings` (the
Parquet table that still includes idle/"No Load" seconds; see
`data_schema.md`). `closures` excludes idle seconds by construction, so
idle-time analysis structurally cannot be built from it.

Both functions load `readings` through a **lazy Polars scan**
(`pl.scan_parquet`) rather than the eager pandas load the rest of the
layer uses, because an eager load of the full table (~274M rows at full
90-day scale) caused out-of-memory failures:

- **`idle_time_per_head`** filters to one head *before* collecting, so
  peak memory is bounded by one head's data (~7.6M rows) rather than the
  whole table. Confirmed via testing: ~99s for all 36 heads at full scale,
  versus 873s+ (with crashes) using an eager load-then-filter approach.
- **`machine_idle_periods_summary`** needs every head's data at each
  timestamp simultaneously (a machine-wide idle period requires all heads
  idle at once), so it can't be chunked by head the way the per-head
  function is. Instead it chunks by calendar week. Confirmed via testing:
  ~16s total, finding 366 real machine-wide idle events across the full
  90-day dataset, versus an out-of-memory crash processing all 90 days in
  one pass.

Both delegate the actual idle-window detection to
`src/closure_detection/detector.py` (`detect_idle_periods`,
`detect_machine_idle_periods`) and only handle the chunking/aggregation
here.

## Known limitations

**`config.yaml`'s `analytics` and `idle_detection` threshold values are
not currently read at runtime.** `moving_average_window`,
`anomaly_zscore_threshold`, `drift_threshold_pct`, and `sustained_seconds`
all exist in `config.yaml` and numerically match each function's own
Python default (and the matching fallback default in
`src/agent/tools.py`'s `TOOL_FUNCTIONS` wiring) - but nothing actually
reads them from the config dict. Changing a threshold today means editing
the Python default (or having the LLM pass an explicit override), not
editing `config.yaml`. This is a gap against the project's own "no
hard-coded thresholds" principle (`architecture.md`), noted here rather
than silently left inconsistent with the rest of the documentation.

## Testing

`tests/test_analytics.py` covers every function in this layer
independently, against small synthetic samples - per `team_rules.md`, no
test here depends on the real AROL data pool.
