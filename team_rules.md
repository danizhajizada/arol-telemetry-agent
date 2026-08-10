# Team Rules & Shared Contract
AROL Telemetry Agent — 3-person project

This document is the single source of truth for how the three of us divide
work and where our code must agree with each other. Read this before writing
code that touches another person's area.

---

## 1. Roles

| Person | Owns | Never touches |
|---|---|---|
| **A** | Ingestion, SQL storage, normalization, closure detection, status classification | LLM code, analytics functions |
| **B** | Deterministic analytics library (the "tools") | SQL, file loading, LLM code |
| **C** | LLM integration, tool schemas, orchestrator, CLI, report formatting | pandas logic, SQL schema |

If you think you need to edit a file outside your area, message the owner
first — don't just change it.

---

## 2. The shared contract (do not change without agreement from all 3)

### 2.1 Database tables (owned by A, read-only for B and C)

- `raw_telemetry` — wide format, one row per second, untouched from CSV.
- `readings` — long format: `timestamp, head_id, count, app_torque, status`
- `closures` — one row per real closure event:
  `timestamp, head_id, count, app_torque, status, status_label, is_reject`

Note: dataset is single-machine. `machine_id` is carried in `raw_telemetry`
for provenance but dropped from `readings`/`closures` onward — no
multi-machine grouping anywhere in the pipeline.

**B and C only ever read `closures` (or `readings`, for idle-only functions).
Neither writes to the database.**

### 2.2 Analytics function contract (owned by B, read-only for C)

Every analytics function:
- Takes `closures` (a DataFrame) as its first argument, plus simple optional
  keyword arguments (e.g. `window`, `threshold`).
- Returns a plain `dict` or a small DataFrame (a handful to a few dozen rows) —
  never the full raw dataframe back.
- Has a one-line docstring describing what question it answers, in plain
  English — C will lean on this almost verbatim for the LLM tool description.

Before adding a new function or changing an existing signature, post it in
the group chat so C can update the matching tool schema.

### 2.3 Tool schema contract (owned by C)

Every function B writes gets one matching entry in `agent/tools.py`
(`TOOL_SCHEMAS` + `TOOL_FUNCTIONS`). If B changes a function's arguments, C
must update the schema in the same day — stale schemas cause silent
tool-call failures.

---

## 3. Coding conventions

- Python 3.11+, one virtual environment per person, `requirements.txt` kept
  in sync.
- No hard-coded file paths, thresholds, or model names — everything reads
  from `config/config.yaml`.
- Every module gets at least one test in `tests/`, using a small synthetic
  sample — no test should require the real AROL data pool to run.
- Log with `logging`, not `print`, for anything other than final CLI output.
- Commit small, pull before you start a session.

---

## 4. Definition of done, per area

**A is done when:** raw CSVs load into `raw_telemetry`, `readings` and
`closures` are correctly populated, the manifest-based freshness check
avoids reprocessing unchanged files, and `tests/` cover closure detection
and status classification against a synthetic sample.

**B is done when:** every function in `analytics/` is implemented, returns
the agreed shape, and is unit-tested independently of A's and C's code.

**C is done when:** the `ask` CLI command takes arbitrary free-text,
correctly picks tool(s) via the LLM for a range of phrasings (not just the
example questions from the spec), produces a structured report, and fails
gracefully (clear message, no crash) when a question can't be answered.

---

## 5. Weekly sync checklist

- Is the `closures` schema still accurate, or has anyone changed it?
- Any new analytics function since last sync? Has its tool schema been added?
- Any test currently failing on `main`?
- What's blocking each person right now?
