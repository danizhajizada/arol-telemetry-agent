# Data Schema

This document defines the exact structure of the data at each stage of
the pipeline, from raw input files through to the tables the analytics
and agent layers operate on.

## Raw input files

One CSV file per machine per day, wide format: one row per second, with
a separate `Count` / `AppTorque` / `Status` column triplet for each
capping head.

| Column pattern | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Polling timestamp (one row per second) |
| `H<NN> Count` | integer | Cumulative closure counter for head NN at this instant |
| `H<NN> AppTorque` | float | Applied torque reading for head NN at this instant |
| `H<NN> Status` | integer | Raw status code for head NN at this instant (see table below) |

With 36 heads, a single file has `1 + 36*3 = 109` columns and one row
per second (86,400 rows for a full day).

### Status codes

| Code | Label | Reject (counts as failure) |
|---|---|---|
| 0 | Closure OK | No |
| 2 | No Load | No |
| 3 | Slow Torque | Yes |
| 4 | No Closure | No |
| 5 | No Closure (reject) | Yes |
| 8 | No InTorque | No |
| 9 | No InTorque (reject) | Yes |
| 16 | No CapTurns | No |
| 17 | No CapTurns (reject) | Yes |
| 32 | Following Error | No |
| 33 | Following Error (reject) | Yes |
| 64 | Bad Closure | No |
| 65 | Bad Closure (reject) | Yes |

## `readings` table (post-ingestion, long format)

One row per `(timestamp, head_id)` - the wide raw format reshaped so
every head's readings live in the same set of columns, one head per row
instead of one head per column group.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Polling timestamp |
| `head_id` | string | e.g. `"H01"` |
| `count` | integer | Cumulative closure counter at this instant |
| `app_torque` | float | Applied torque at this instant |
| `status` | integer | Raw status code (see table above) |

This table includes every second, including seconds where a head is
idle (status 2, counter unchanged) - it is the input to idle-time
analysis specifically, which needs to see those gaps.

## `closures` table (post closure-detection)

One row per **detected real closure event** - a second where a head's
counter genuinely increased versus the previous reading, not every
second of raw polling.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Timestamp of the closure event |
| `head_id` | string | e.g. `"H01"` |
| `count` | integer | Counter value at the closure |
| `app_torque` | float | Applied torque recorded for this closure |
| `status` | integer | Raw status code |
| `status_label` | string | Human-readable status (e.g. `"Closure OK"`, `"Bad Closure"`) |
| `is_reject` | boolean | Whether this status code is classified as a failure (see table above) |

This is the table nearly every analytics function operates on. Idle
seconds (status 2) are excluded by construction - a head reporting "No
Load" has an unchanged counter, so it never produces a row here.

### `is_reject` vs. `status_label == "Closure OK"`

Two related but distinct filters are used depending on the question
being asked:

- **`is_reject == False`** answers "was this closure a confirmed
  failure?" - used for success-rate calculations, since several status
  codes (e.g. "No Load") are not confirmed failures under the plant's
  own classification, even though they aren't a clean "OK" either.
- **`status_label == "Closure OK"`** answers "was this a genuinely clean
  reading?" - used specifically for torque-value calculations. A
  meaningful fraction of "not rejected" closures (status 2, roughly 40%
  of the raw dataset before closure detection) have a torque reading of
  exactly 0.0, since no load was on the sensor at that instant; including
  these in a torque *average* would understate real applied torque, even
  though they are not failures for success-rate purposes.

This distinction was found through direct investigation of an
unexpectedly low torque average, and is applied consistently across the
analytics layer: success/failure metrics use `is_reject`; torque-value
metrics use `status_label == "Closure OK"`.

## Configuration-driven values

Nothing in the tables above is hard-coded in application code - the
status-code table, column-name suffixes for the raw wide format, and
all analysis thresholds (idle duration, anomaly z-score, drift window)
are defined in one configuration file and read at runtime, so the
system can be pointed at a differently-shaped dataset without code
changes.
