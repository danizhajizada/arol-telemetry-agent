# AROL Telemetry Agent

An AI-assisted telemetry analysis system for AROL capping machines.

The project processes raw machine telemetry, reconstructs valid capping events, performs deterministic diagnostic analysis, and uses an LLM-based agent to generate explainable reports for engineers.

## Overview

The system is built as a three-stage pipeline:

```text
Raw telemetry CSV files
        ↓
Data Ingestion & Normalization
        ↓
Closures / Readings
        ↓
Deterministic Analytics
        ↓
LLM Agent
        ↓
Diagnostic Report
```

Each stage has a separate responsibility:

- **Ingestion layer** — loads, cleans, validates and restructures raw telemetry.
- **Analytics layer** — calculates KPIs, torque statistics, anomalies, trends, correlations and idle periods.
- **Agent layer** — interprets user questions, selects the appropriate analytics tools and generates a human-readable report.

The LLM does not directly analyse the raw telemetry. Numerical results are produced by deterministic Python functions and then passed to the agent.

## Data Pipeline

The supplied dataset contains:

- 89 telemetry CSV files
- 36 capping heads
- ~7.6 million raw telemetry rows
- 109 original telemetry columns
- ~274 million normalized readings
- ~55 million reconstructed counter-advance records

Raw telemetry is provided in wide format, with separate `Count`, `AppTorque` and `Status` columns for every head.

The ingestion pipeline converts this into a long-format structure:

```text
timestamp
machine_id
head_id
count
app_torque
status
source_file
```

## Counter-Advance Detection

The machine counters are cumulative.

A positive counter difference normally indicates that the head performed one or more operations.

However, temporary telemetry dropouts were found in the source data, for example:

```text
184390 → 0 → 184390
```

Without additional validation, the recovery from zero could incorrectly appear as 184,390 new operations.

A counter advance is therefore considered valid only when:

```text
current_count > previous_count
previous_count > 0
current_count > 0
```

This prevents temporary zero states from producing artificial events.

Positive jumps greater than one are preserved using `count_increment` rather than being expanded into fabricated individual events.

## Readings and Closures

The pipeline produces two main datasets.

### Readings

The complete normalized telemetry, including periods where counters do not change.

Used for:

- idle-time analysis
- telemetry-gap analysis
- machine-state analysis
- time-series diagnostics

### Closures

Valid counter-advance records reconstructed from the cumulative counters.

Used for:

- success-rate analysis
- torque statistics
- anomaly detection
- drift analysis
- head comparison
- diagnostic reports

A counter advancement does not automatically mean a successful bottle closure.

Status and torque are used to distinguish events such as:

- `Closure OK`
- `No Load`
- Reject / diagnostic states

## Storage

The project uses a hybrid storage approach:

- **SQLite** — raw telemetry and counter-advance records
- **ZSTD-compressed Parquet** — high-volume normalized readings

Parquet was selected because the normalized dataset contains hundreds of millions of rows and is primarily used for analytical queries.

Compared with row-oriented storage, Parquet significantly reduced storage requirements and improved analytical loading performance.

## Performance

The ingestion pipeline was migrated from pandas to **Polars** for higher processing performance.

Full preprocessing of the 89-file dataset was reduced from approximately:

```text
Pandas: ~14.3 minutes
Polars: ~9 minutes
```

This represents roughly a **37% reduction in preprocessing time** while preserving equivalent analytical results.

Parquet also provides significantly faster loading for analytical workloads compared with the original row-oriented storage approach.

## Incremental Processing

A manifest tracks the source CSV files using their file size and modification time.

The pipeline detects:

- new files
- changed files
- removed files
- unchanged files

Unchanged data can therefore reuse the existing processed cache instead of running the complete preprocessing pipeline again.

Counter continuity is also preserved across CSV file boundaries by retaining the final reading for each head and comparing it with the first reading of the following file.

## Analytics

The deterministic analytics layer contains functions for:

- overall and per-head success rates
- torque statistics
- torque distributions
- moving averages
- torque drift detection
- statistical anomaly detection
- head-to-head correlation
- capping speed
- per-head idle time
- machine-wide idle time
- diagnostic visualizations

Analytics functions return small dictionaries or short tables rather than the complete dataset.

## Agent

The agent accepts free-text diagnostic questions such as:

```text
Which head has the most problems and why?
```

The LLM decides which analytical tools are required, executes them through the deterministic analytics layer, and combines the results into an explainable report.

The LLM is responsible for:

- interpreting the question
- selecting tools
- deciding whether additional analysis is required
- generating the final explanation

The LLM does **not** calculate the underlying numerical results.

## Usage

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Place the telemetry files in the configured data-pool directory.

Then run the CLI.

### Ask a question

```bash
python -m src.cli ask "Which head has the most problems and why?"
```

### Generate a predefined report

```bash
python -m src.cli report kpi
python -m src.cli report anomalies
python -m src.cli report drift
```

### Interactive mode

```bash
python -m src.cli chat
```

## Testing

Run the project tests with:

```bash
pytest
```

Regression tests cover areas including:

- transient zero-counter states
- multi-increment preservation
- telemetry gaps
- cross-file counter continuity
- status classification
- incremental processing
- Parquet-backed readings
- per-head idle detection
- machine-wide idle detection

## Design Principle

The central principle of the project is:

> **Preserve what the telemetry actually shows without inventing observations that are not present.**

Missing telemetry is not interpolated, temporary counter dropouts are not interpreted as real operations, and unknown machine states are not fabricated.

## Project Structure

```text
src/
├── ingestion/
├── analytics/
├── agent/
└── cli.py

config/
└── config.yaml

data/
└── .cache/
    ├── telemetry.db
    ├── manifest.json
    └── readings/
```

## Authors


Developed as part of the AROL Capping Diagnostics SDP project.

Daniz Hajizada, Bedoya Diaz Santiago, Al-kubaisi Ameer
