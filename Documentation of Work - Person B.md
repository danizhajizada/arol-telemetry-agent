# AROL Telemetry Agent — Analytics Layer: Findings, Fixes, and Function Documentation
### Person B — Deterministic Analytics Library

## 1. Scope

Person B owns `src/analytics/` (`kpi.py`, `trend.py`, `anomaly.py`, `correlation.py`):
a deterministic function library exposed as "tools" to the LLM orchestrator
(`src/agent/tools.py`, owned by Person C). Every function takes the
`closures` DataFrame (produced by Person A's ingestion/detection pipeline)
as its first argument and returns a small `dict` or DataFrame — never raw
data back. Per `team_rules.md`, B never writes to the database and never
touches ingestion/SQL/LLM code.

## 2. Dependency on Person A's preprocessing — what analytics must assume

Person A's documentation ("Documentation of Work - Person A") establishes
how the `closures` table is built from raw telemetry. The following
properties of that table directly shape how analytics functions must be
written; they are not optional implementation details.

### 2.1 A "closure" row is a counted head cycle, not necessarily a successful bottle closure

`closures` contains every row where the per-head counter validly advanced
(`count_increment > 0`, with both the previous and current counter > 0, to
exclude transient zero-state telemetry dropouts). That includes three kinds
of rows:

- **Closure OK** (`status_label == "Closure OK"`) — a real capping cycle,
  torque applied (~2 Nm in the real dataset).
- **No Load** (`status_label == "No Load"`) — the head cycled but no cap
  was present. `is_reject` is `False` (it's not a failure), but
  `app_torque` is ~0. In the real 3-month dataset this is **~42.6%** of all
  reconstructed +1 cycles — not a rare edge case.
- **Reject statuses** (`is_reject == True`) — genuine failures (slow
  torque, no closure, following error, bad closure, etc). Rare in the real
  dataset (~1,096 out of ~55.1M closure/counter-advance records).

**Consequence for analytics:** filtering on `is_reject` alone is not enough
to isolate "real closures with meaningful torque." `is_reject == False`
includes both real OK closures and zero-torque No Load cycles. Any function
that touches `app_torque` needs to filter to `status_label == "Closure OK"`
specifically — see §4.

### 2.2 `count_increment` can be greater than 1

When the counter jumps by more than 1 between two observed telemetry rows
(most often across a timestamp gap), the row is preserved with
`count_increment > 1` but still only **one** torque/status reading — A's
pipeline does not fabricate the missing intermediate cycles. Any KPI that
means "how many physical pieces/cycles happened" must sum `count_increment`,
not count rows. Any KPI that means "what did torque look like on this
observation" is correctly computed per row, since there is no finer-grained
torque data to use instead.

### 2.3 Timestamps can have large gaps within a single head's sequence

Gaps up to ~8 hours occur between consecutive rows for the same head. Trend
functions that operate on "row order" (rolling windows, z-scores) should be
read as trends across *observed* closures, not across evenly-spaced time —
two adjacent rows in a rolling window may be hours apart in reality.

### 2.4 Scale

The real dataset (89 files, Feb–Apr 2026) produces **~55.1M** closure/
counter-advance records across 36 heads. All functions here were only ever
validated against small synthetic samples (a handful of rows) before this
review — see §6 for the plan to validate against the real pool once it's
available locally.

## 3. Bugs found and fixed in this pass

These were found by adding the two previously-missing unit tests
(`moving_average`, `capping_speed_incremental`) and running the full suite
against the actual installed pandas version (3.0.5), not by inspection.

### 3.1 `capping_speed_incremental` crashed on every real dataset (critical)

Original code did:
```python
group["capping_speed_pph"] = (piece_index / elapsed_hours.replace(0, pd.NA)).astype(float)
```
`elapsed_hours.replace(0, pd.NA)` turns the series into `object` dtype
(mixed float + `pd.NA`), and `.astype(float)` on that raises `TypeError` in
pandas 3.0. Since the **first** closure of every head has `elapsed_hours ==
0` by construction (it's the reference point), this path is hit on every
run, for every head — i.e. the function was unusable on any real data.
Fixed by replacing with plain `float("nan")` instead of `pd.NA`, which keeps
the series as a normal float64 column.

### 3.2 `capping_speed_incremental` also broke under pandas 3.0's `groupby.apply` (critical, compounding bug)

Independently of §3.1, pandas 3.0 changed `DataFrameGroupBy.apply()` so the
grouping column (`head_id`) is no longer included in the sub-DataFrame
passed to the applied function. The final column selection
(`df.groupby(...).apply(...)[["timestamp", "head_id", ...]]`) then raised
`KeyError: "['head_id'] not in index"`. Fixed by rewriting the whole
function without `.apply()` — using `groupby(...).transform("min")` and
`groupby(...).cumcount()` — which is also simpler and faster.

### 3.3 `capping_speed_incremental` used row count instead of real piece count (correctness bug, not just a pandas-version issue)

Even after §3.1/§3.2, the function counted **rows** (`cumcount() + 1`) as
"pieces produced." Per §2.2, a single row can represent several physical
cycles when `count_increment > 1`. Fixed to accumulate
`count_increment.cumsum()` instead, so throughput reflects actual counter
advancement, not telemetry-row count.

### 3.4 Flaky test: `test_zscore_anomalies_flags_outlier`

Not a code bug — a pre-existing test threshold issue. The sample outlier's
z-score is exactly `1.4142`; the test asserted `threshold=1.5`, which the
outlier never clears (pure arithmetic, independent of pandas version).
Lowered the test threshold to `1.4`.

## 4. The "Closure OK" filter — what changed and why

Per §2.1, every function that reads `app_torque` was changed to filter on
`status_label == "Closure OK"` instead of (or in addition to) `is_reject`,
so that zero-torque **No Load** rows don't distort the result:

| Function | Before | After |
|---|---|---|
| `kpi.torque_stats` | `~is_reject` when `successful_only=True` | `status_label == "Closure OK"` when `successful_only=True` |
| `kpi.torque_distribution` | `~is_reject` when `successful_only=True` | `status_label == "Closure OK"` when `successful_only=True` |
| `anomaly.zscore_anomalies` | no filter (all rows) | always restricted to `status_label == "Closure OK"` |
| `trend.moving_average` | no filter (all rows) | always restricted to `status_label == "Closure OK"` |
| `trend.detect_drift` | no filter (all rows) | always restricted to `status_label == "Closure OK"` |
| `correlation.head_torque_correlation` | no filter (all rows) | always restricted to `status_label == "Closure OK"` |

Why this matters concretely, using the real status/torque distribution from
Person A's analysis (Status 0 mean ≈ 2.01 Nm, Status 2 mean ≈ 0.001 Nm,
~43% of rows are Status 2):

- **`torque_stats`/`torque_distribution`**: without the fix, ~43% of the
  "successful" population would be near-zero-torque No Load rows, pulling
  the mean/min/std toward zero and producing a bimodal histogram that
  doesn't represent real closure torque at all.
- **`zscore_anomalies`**: a mixed population (Closure OK + No Load) is
  bimodal (~0 Nm and ~2 Nm clusters). Z-score thresholding assumes a
  roughly unimodal distribution — on a bimodal one it produces statistically
  meaningless flags (it would likely flag many normal Closure OK rows while
  missing real reject outliers).
- **`moving_average`/`detect_drift`**: a rolling mean over a mix of ~0 Nm
  and ~2 Nm values tracks the *changing proportion* of No Load vs Closure OK
  cycles in the window, not real torque drift.
- **`head_torque_correlation`**: two heads that happen to go idle
  (No Load) at the same time would show artificially high correlation from
  shared idle periods, not from a real mechanical relationship.

`success_rate`, `success_rate_per_head`, and `success_rate_over_time` were
**deliberately left unchanged** — see §5.1, this is a different, more
debatable question than the torque-zero-value issue above.

## 5. Open questions for the team (not changed unilaterally)

### 5.1 Should No Load cycles count toward "total closures" in success_rate?

Currently `success_rate*` counts every row with `is_reject == False` as
"successful," which includes No Load cycles. On the real dataset this
means success rate will read as ~99.998% (only ~1,096 real rejects in
~55.1M records) — not because anything is broken, but because "success" is
currently defined as "not a rejected cycle," and No Load cycles (which
aren't capping attempts at all — no cap was present) inflate the
denominator. Whether the brief's "% successful capping operations" should
exclude No Load from the denominator entirely is a team decision, not a
clear-cut bug like §4 — reasonable people could define "operation" either
way. Flagging for discussion before changing a shared KPI's meaning per
`team_rules.md` §2.2.

### 5.2 Should No Load cycles count as "pieces" in capping_speed_incremental?

Related question: after fixing §3.3, `capping_speed_incremental` sums
*all* `count_increment` regardless of `status_label`, including No Load
cycles. If "capping speed" is meant to measure actual pieces capped, No
Load cycles arguably shouldn't count. Left unchanged pending team
discussion, same reasoning as §5.1.

## 6. Function reference

### `kpi.py`

- **`success_rate(closures)`** → `dict`. Overall total/successful/failed
  counts and success rate %. "Successful" = `is_reject == False` (see §5.1
  for the open question about No Load).
- **`success_rate_per_head(closures)`** → `DataFrame`, one row per
  `head_id`. Same success definition as above, broken out by head.
- **`success_rate_over_time(closures, freq="D")`** → `DataFrame` indexed by
  time bucket (`freq` is any pandas offset alias, e.g. `"D"`, `"h"`). Same
  success definition, broken out by period.
- **`torque_stats(closures, successful_only=True)`** → `dict` with
  count/mean/min/max/std of `app_torque`. When `successful_only=True`
  (default), restricted to `status_label == "Closure OK"` (§4).
- **`torque_distribution(closures, bins=10, successful_only=True)`** →
  `DataFrame` histogram (`bin_start`, `bin_end`, `count`). Same
  `successful_only` semantics as `torque_stats`.
- **`capping_speed_incremental(closures)`** → `DataFrame` with a running
  pieces/hour figure per head, based on cumulative `count_increment` over
  elapsed time since that head's first observed closure (§3.3). First row
  per head is `NaN` (zero elapsed time by construction).

### `trend.py`

- **`moving_average(closures, window)`** → `DataFrame` with a rolling mean
  of `app_torque` per head over `window` closures. Restricted to
  `status_label == "Closure OK"` (§4).
- **`detect_drift(closures, window=50, drift_threshold=0.1)`** →
  `DataFrame`, one row per head whose rolling-average torque changed by at
  least `drift_threshold` (fractional) between the start and end of the
  observed period. Restricted to `status_label == "Closure OK"` (§4).

### `anomaly.py`

- **`zscore_anomalies(closures, threshold=3.0)`** → `DataFrame` of
  individual closures whose torque is `threshold` standard deviations or
  more from that head's mean. Restricted to `status_label == "Closure OK"`
  before computing the z-score (§4) — otherwise the bimodal Closure
  OK/No Load mix breaks the z-score's unimodal assumption.

### `correlation.py`

- **`head_torque_correlation(closures)`** → `DataFrame`, pairwise Pearson
  correlation matrix of `app_torque` across heads, aligned by closure order
  (`cumcount` per head, not wall-clock time — heads close at different
  rates). Restricted to `status_label == "Closure OK"` (§4).

## 7. Test coverage

`tests/test_analytics.py` — 15 tests covering every function in `analytics/`
independently, using small synthetic samples (per `team_rules.md`, no test
depends on the real AROL data pool). All 24 project tests (including
Person A's and the pipeline tests) pass as of this writing.

Two tests were added in this pass that did not previously exist:
`test_moving_average_computes_per_head_rolling_mean` and
`test_capping_speed_incremental_computes_pieces_per_hour` — the latter is
what surfaced the three bugs in §3.

## 8. Validating against real data — next step

`data/` currently contains no real CSVs locally (only `.gitkeep`), so
nothing above has been validated against the actual ~55M-row dataset yet,
only against synthetic samples. Plan once real CSVs are available:

1. Place CSVs in a local folder and point `config/config.mytest.yaml`
   (`data_pool.folder`) at it, with its own `database.path`/
   `manifest_path` so it never touches the shared `data/` cache.
2. Load the resulting `closures` DataFrame directly (via
   `src.cli._load_config` + `src.cli._prepare_closures`, no LLM/API key
   needed) and call each analytics function by hand.
3. Sanity-check against Person A's own real-data numbers where they
   overlap: `torque_stats(successful_only=True)` should land close to
   Status 0's mean ≈ 2.01 Nm (not ≈0, which would indicate the Closure OK
   filter isn't taking effect); `zscore_anomalies` should flag a small
   number of rows concentrated in/near the ~1,096 known reject records, not
   a large fraction of normal closures.
