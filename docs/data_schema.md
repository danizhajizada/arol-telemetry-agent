# Data Schema

## 1. Purpose

This document defines the project’s data model from the raw AROL telemetry files through the normalized telemetry and reconstructed counter-advance datasets used by the analytics and agent layers.

The design has three goals:

- preserve the telemetry exactly as observed;
- provide a consistent schema for downstream analysis; and
- handle the scale of the supplied dataset without loading the full telemetry pool into memory at once.

The current persistence architecture is:

```text
Raw CSV telemetry
        |
        v
     Ingestion
        |
        +--> raw_telemetry  -> SQLite
        |
        +--> readings       -> ZSTD Parquet
        |
        +--> valid counter advances
                  |
                  v
             closures       -> ZSTD Parquet
```

The names `readings` and `closures` describe the logical datasets exposed to downstream code. In the current implementation, both derived datasets are stored as Parquet files.

---

## 2. Raw Telemetry Input

The supplied data pool contains daily CSV telemetry files in wide format. Each row is a machine telemetry snapshot, normally sampled once per second.

For the supplied machine, the raw schema contains:

- one timestamp column;
- 36 cumulative `Count` columns;
- 36 `AppTorque` columns; and
- 36 `Status` columns.

This gives 109 original telemetry columns.

### 2.1 Raw column pattern

| Column pattern | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Telemetry polling timestamp |
| `H<NN> Count` | integer | Cumulative counter for capping head NN |
| `H<NN> AppTorque` | float | Applied torque reading for head NN |
| `H<NN> Status` | integer | Raw closure/status code for head NN |

During ingestion, provenance information is added so records remain traceable to their source file and machine.

### 2.2 Status codes

| Code | Label | Reject |
|---:|---|---|
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

The status mapping is configuration-driven and is attached to reconstructed counter-advance records during classification.

---

## 3. Normalized `readings` Dataset

The wide telemetry is reshaped into a long-format dataset with one row per `(timestamp, head_id)`.

This converts the repeated head-specific column groups into one common schema that can be processed consistently by downstream functions.

### 3.1 Schema

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Telemetry polling timestamp |
| `machine_id` | string | Machine identifier derived during ingestion |
| `head_id` | string | Capping-head identifier, e.g. `H01` |
| `count` | integer | Cumulative counter at this instant |
| `app_torque` | float | Applied torque at this instant |
| `status` | integer | Raw status code |
| `source_file` | string | Source CSV used to generate the row |

The `readings` dataset preserves the complete observed telemetry sequence after normalization, including rows where:

- the counter does not advance;
- the head is in `No Load`;
- torque is zero; or
- the machine is otherwise idle.

This is important because some analyses, especially idle-state detection and timestamp continuity checks, require the full time series rather than only rows where the counter changes.

### 3.2 Storage

Normalized readings are persisted as ZSTD-compressed Parquet files. Processing is performed one source file at a time to keep memory use bounded.

Conceptually:

```text
data/.cache/readings/
├── telemetry_..._2026-02-01.parquet
├── telemetry_..._2026-02-02.parquet
└── ...
```

---

## 4. Reconstructed `closures` Dataset

The dataset historically named `closures` is more precisely interpreted as a dataset of **observed valid counter-advance records**.

A row is retained when a head’s cumulative counter increases relative to its previous observed value and both counter values are greater than zero.

```text
count_increment = current_count - previous_count

valid_advance =
    count_increment > 0
    AND current_count > 0
    AND previous_count > 0
```

The non-zero requirement is important because the raw telemetry contains temporary zero states such as:

```text
184390 -> 0 -> 184390
```

A naive difference calculation would interpret the recovery from `0` to `184390` as 184,390 new operations. The implemented rule prevents this false event generation.

A counter advance represents observed machine activity, but it does **not** automatically mean that one successful bottle closure occurred. The associated status and torque values must be used to interpret the outcome.

### 4.1 Schema

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | datetime | Timestamp of the observed counter advance |
| `head_id` | string | Capping-head identifier |
| `count` | integer | Current cumulative counter value |
| `count_increment` | integer | Increase since the previous valid observed counter |
| `time_since_prev_seconds` | numeric | Elapsed time since the previous telemetry observation for the same head |
| `app_torque` | float | Torque value observed on the retained telemetry row |
| `status` | integer | Raw status code |
| `status_label` | string | Human-readable status |
| `is_reject` | boolean | Whether the status is classified as a reject |

The `closures` dataset is the main input to the deterministic analytics layer and is persisted as ZSTD-compressed Parquet.

Conceptually:

```text
data/.cache/closures/
├── telemetry_..._2026-02-01.parquet
├── telemetry_..._2026-02-02.parquet
└── ...
```

---

## 5. Interpretation of Counter Advances

A counter advance represents observed machine activity, but it must not automatically be interpreted as one successful bottle closure.

The outcome is determined by the associated status and torque values.

```text
counter advance
      |
      v
counted head cycle
      |
      +--> inspect status
      |
      +--> inspect torque
      |
      v
interpret outcome
```

Two common cases are:

- `Closure OK`: a clean closure status, normally associated with meaningful torque;
- `No Load`: the head counter advanced while no load was present.

Therefore, downstream code should not assume that every row in `closures` is equivalent to a successful capping operation.

### 5.1 `is_reject` versus `Closure OK`

These fields answer different questions:

- `is_reject == False` means that the status is not classified as a reject;
- `status_label == "Closure OK"` selects only clean closure-status observations.

This distinction is especially important for torque analysis. `No Load` records are normally associated with torque close to zero, so including them in torque statistics would distort:

- average torque;
- torque distributions;
- anomaly detection;
- moving averages; and
- drift analysis.

For torque-oriented analytics, clean `Closure OK` observations are therefore the appropriate population.

---

## 6. Multi-Increment Records

`count_increment` may be greater than one.

For example:

```text
previous count = 500
current count  = 503
count_increment = 3
```

This means that three counter increments occurred between two observed telemetry rows.

The pipeline does **not** create three artificial event rows because their individual timestamps, torque values and status values were not observed.

Instead, the record remains:

```text
timestamp                <observed final timestamp>
count                    503
count_increment          3
time_since_prev_seconds  <measured elapsed time>
app_torque               <observed torque>
status                   <observed status>
```

This preserves what the telemetry actually proves while avoiding fabricated event-level detail.

Large multi-increment values may occur across long telemetry gaps. In such cases, the counter change can still show that activity occurred, but the timing and measurements of the individual intermediate cycles remain unknown.

---

## 7. Timestamp Continuity and Missing Telemetry

The telemetry is normally sampled once per second, but the supplied dataset contains timestamp gaps.

A timestamp gap means that no telemetry row exists for part of the time sequence. This is different from a recorded row containing zero values.

```text
Timestamp gap
= no telemetry observation exists

Zero/default telemetry state
= a telemetry observation exists, but one or more values are zero
```

Missing telemetry is not interpolated. The pipeline does not invent:

- intermediate timestamps;
- missing torque values;
- missing status values; or
- individual cycle events.

The elapsed time between observed records is retained through `time_since_prev_seconds`.

Large timestamp gaps also interrupt confirmed idle-state runs because machine state is unknown while telemetry is absent.

---

## 8. Data Validation and Cleaning Rules

Before reconstructed counter advances are produced, the normalized telemetry is checked for data-quality issues.

The implemented checks include:

- empty normalized datasets;
- missing `count`, `app_torque`, or `status` values;
- duplicate `(timestamp, head_id)` rows;
- counter decreases;
- timestamp continuity issues; and
- invalid zero-state transitions that could create false positive counter advances.

True duplicate normalized rows can be removed by the dedicated duplicate-cleaning step.

Counter decreases are not silently deleted from the raw data. They remain traceable because some decreases are caused by temporary telemetry zero states rather than real physical counter resets.

The overall principle is:

> Preserve observed source data, but prevent known telemetry artifacts from being misinterpreted as physical machine events.

---

## 9. Cross-File Counter Continuity

Source CSV files are processed one at a time, but a valid counter increase may occur between the final row of one file and the first row of the next.

To preserve continuity, the final normalized row for each head is retained as a small `previous_tail`.

```text
File A
...
last row for H01 = count 100
        |
        v
previous_tail
        |
        +---- prepended to File B
                      |
                      v
File B first row for H01 = count 101
                      |
                      v
detected increment = 1
```

This allows the system to detect cross-file counter changes without loading the complete normalized dataset into memory at once.

---

## 10. Persistence and Incremental Processing

The persistence layer uses different storage formats for different access patterns.

### 10.1 Raw telemetry

Raw telemetry is retained in SQLite.

This supports:

- provenance;
- incremental synchronization;
- source-file replacement; and
- removal of rows belonging to deleted source files.

### 10.2 Derived analytical datasets

The high-volume derived datasets are stored as compressed Parquet:

```text
readings -> ZSTD Parquet
closures -> ZSTD Parquet
```

Parquet is appropriate for these datasets because downstream analysis usually reads a subset of columns across a very large number of rows.

### 10.3 Manifest

A manifest stores a lightweight signature for every source CSV, based on file metadata such as file size and modification time.

Before preprocessing, the current input pool is compared with the saved manifest.

The pipeline identifies:

- new files;
- changed files;
- removed files; and
- unchanged files.

If the source pool is unchanged, the cached derived datasets can be reused instead of running the complete ingestion pipeline again.

The current cache layout is:

```text
data/.cache/
├── telemetry.db
├── manifest.json
├── readings/
│   ├── <source-file>.parquet
│   └── ...
└── closures/
    ├── <source-file>.parquet
    └── ...
```

---

## 11. Scale of the Validated Dataset

The ingestion and reconstruction logic was previously validated on the complete supplied telemetry pool.

The validated dataset contained:

```text
Source files:             89
Raw rows:                  7,623,968
Normalized readings:     274,462,848
Counter-advance records:  55,128,924
Represented increments:   55,888,498
Maximum count_increment:        6766
```

These values describe the validated logical output of the ingestion and reconstruction pipeline.

The persistence architecture has since been updated so that `closures`, like `readings`, is stored in ZSTD-compressed Parquet rather than SQLite. The logical schema and counter-advance semantics remain unchanged.

---

## 12. Downstream Data Contract

The ingestion layer exposes two main datasets to the rest of the application.

### `readings`

Used when the analysis requires the full normalized telemetry sequence, for example:

- idle detection;
- telemetry-gap reasoning;
- status continuity; or
- analyses that require unchanged-counter periods.

### `closures`

Used when the analysis requires reconstructed counter-advance activity, for example:

- success-rate KPIs;
- torque statistics;
- capping speed;
- trend and drift analysis;
- anomaly detection;
- head comparison; and
- report generation.

This separation keeps downstream logic clear:

```text
full time-series question
        -> readings

counter-advance / capping question
        -> closures
```

---

## 13. Configuration-Driven Behaviour

Dataset-specific behavior is controlled through configuration rather than being embedded directly into the schema.

Configured values include:

- data-pool path and file pattern;
- raw column suffixes;
- status-code mapping;
- idle-status code;
- sustained idle duration;
- allowed telemetry-gap tolerance;
- database path;
- manifest path; and
- analysis thresholds used elsewhere in the application.

This keeps the schema stable while allowing the pipeline to be adapted to other compatible telemetry pools without redesigning downstream interfaces.

---

## 14. Summary

The project uses a layered data model:

```text
Raw wide CSV telemetry
        |
        v
Normalized readings
(one row per timestamp/head)
        |
        v
Validated counter advances
(one row per observed valid advance)
        |
        v
Analytics and report agent
```

The design deliberately separates raw observations from derived interpretations.

The most important rules are:

- raw telemetry is preserved rather than rewritten;
- temporary zero-counter states must not generate false events;
- counter advances greater than one are preserved rather than expanded into invented rows;
- missing telemetry is not interpolated;
- cross-file counter continuity is maintained;
- `No Load` is not equivalent to `Closure OK`; and
- the high-volume analytical datasets are persisted in compressed Parquet for efficient downstream use.

This schema provides the stable contract between ingestion, analytics, and agent orchestration while preserving the meaning and limitations of the original telemetry.
