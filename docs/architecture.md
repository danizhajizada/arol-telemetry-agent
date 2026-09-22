# System Architecture

## Overview

The system is a pipeline with three stages, each owning a distinct
responsibility, connected by a small number of well-defined data
contracts rather than tight coupling:

```
Raw telemetry (CSV files)
        |
        v
   INGESTION            -- loads, validates, deduplicates, detects
                           real closure events from noisy per-second data
        |
        v
   closures / readings   -- two persisted tables, different shapes
        |
        v
   ANALYTICS LAYER        -- deterministic functions: KPIs, trends,
                            anomalies, plots - the agent's "tools"
        |
        v
   AGENT LAYER            -- LLM-driven orchestration: interprets a
                            free-text question, decides which analytics
                            functions to call, synthesizes a report
        |
        v
   CLI / user-facing report
```

Each layer only depends on the layer below it through its data
contract, not its implementation - the analytics layer never knows how
ingestion works internally, and the agent layer never touches pandas or
Polars directly.

## Ingestion layer

Responsible for turning raw, high-frequency telemetry into two
persisted, query-ready tables (see `data_schema.md` for exact column
definitions):

- **Reshaping**: raw files are wide-format (one row per second, with a
  separate `Count`/`AppTorque`/`Status` triplet of columns per head).
  Ingestion reshapes this into long format - one row per
  `(timestamp, head_id)` - which every downstream function expects.
- **Closure detection**: a physical capping event is identified by an
  increase in a head's cumulative counter between consecutive readings,
  not by any single reading in isolation. Seconds where the counter
  doesn't change are noise from over-polling relative to the actual
  production rate, and are correctly excluded rather than treated as
  separate events.
- **Deduplication**: exact duplicate `(timestamp, head_id)` rows are
  removed.
- **Incremental processing**: raw files are processed one at a time
  rather than concatenated into memory as a single large in-memory
  table before processing - this keeps memory usage bounded regardless
  of how many files are in the data pool, and lets ingestion resume/add
  new files without reprocessing everything from scratch.

## Storage

Two tables are persisted after ingestion, in a columnar, compressed
format (Parquet):

- **`readings`**: the full long-format per-second data, including idle
  ("No Load") seconds. Used specifically by idle-detection analysis,
  which needs to see the gaps closure detection deliberately excludes.
- **`closures`**: one row per detected real closure event - the table
  nearly every other analysis function operates on.

A columnar format was chosen over a row-oriented database specifically
because typical analysis queries touch a small number of columns across
many rows (e.g. "average torque across all closures") rather than
needing full-row lookups - measured directly during development: loading
the full closures table (55M+ rows) from a row-oriented store took
70-100+ seconds; the equivalent Parquet-based load takes ~1-2 seconds,
roughly a 50x difference on this dataset.

## Analytics layer

A library of deterministic, stateless functions - never involving the
LLM - that each answer one well-defined question against `closures` or
`readings`: overall/per-head success rates, torque statistics and
distributions, trend/drift detection, anomaly detection (statistical
outliers), idle-time analysis, and chart generation.

Every function follows the same contract: take the relevant table (plus
simple optional filters - a head ID, a date range, a threshold) as
input, and return either a small dictionary or a short table - never
the full underlying dataset. This matters because the agent layer sends
whatever a function returns directly to the LLM as context; a function
that returned millions of raw rows would be both too slow to use
interactively and unusable as LLM context.

Plotting functions follow the same shape, with one difference: instead
of returning data directly, they render a chart, save it as an image
file, and return the file path plus a few summary statistics - the
image itself is never sent to the LLM.

## Agent layer

The layer that turns a free-text question into a report, described in
full in `agent_decision_flow.md`. In summary: a large language model is
given a plain-text description of every available analytics function
(never their code) and decides, based on the user's question, which
function(s) to call and in what order - including calling several in
sequence when one result suggests a follow-up check is needed. The
functions themselves execute normally in this codebase; only the
decision of *which* to run, and the final written explanation, comes
from the model.

## CLI (user-facing interface)

Three ways to interact with the system:

- **`ask <question>`** - a single free-text question, one-shot.

  ```
  python -m src.cli ask "which head has the most problems and why?"
  ```
- **`report <kind>`** - a small set of named, pre-defined questions
  (e.g. an overall KPI summary) routed through the same agent loop as
  `ask`.

  ```
  python -m src.cli report kpi
  python -m src.cli report anomalies
  python -m src.cli report drift
  ```
- **`chat`** - an interactive session where the underlying data is
  loaded once and reused across multiple questions, rather than reloaded
  for every question - meaningful given the dataset's size, where
  reloading on every question would make an interactive session
  impractically slow.

  ```
  python -m src.cli chat
  ```

  Once started, the session prompts for a question, prints the answer,
  then prompts again - type `exit` or `quit` to end the session.
  ```
  You: what is the overall success rate?
  <report printed here>
  You: what is the idle time for each head?
  <report printed here>
  You: exit
  ```

Every report, regardless of entry point, is automatically saved to disk
in a consistent template (see `sample_reports/report_template.md`) and
also printed to the console.

## Design principles reflected throughout

- **No hard-coded paths, thresholds, or model names.** Everything
  environment- or dataset-specific (file locations, status-code
  meanings, LLM model choice, token limits) lives in one configuration
  file, not scattered through the code.
- **Deterministic computation, non-deterministic orchestration.** Every
  number in a report comes from ordinary, testable Python/data-processing
  code; only the choice of *which* computation to run, and the
  natural-language explanation, involves the LLM. This keeps the system
  auditable - any reported number can be traced back to a specific,
  inspectable function call.
- **Graceful degradation over hard failure.** A tool that errors, an
  out-of-scope question, or empty input all produce a clear, honest
  response rather than a crash or a fabricated answer - each verified
  directly through testing rather than assumed.
