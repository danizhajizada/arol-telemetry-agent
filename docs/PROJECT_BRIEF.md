# Project Brief — AROL Telemetry Agent (Polito SDP, Project Q3)

## 1. Context

AROL capping machines expose several measurable data families: machine status/alarms,
production rate/downtime, OEE indicators, energy metering, and **torque/closure
diagnostics**. This project scopes down to **torque/closure diagnostics only**.

## 2. Note on the two source documents

The AROL slide deck and the official Polito brief describe the same assignment with
different architectural framing:

- **AROL deck**: asks for an "Agentic AI application" — a single LLM **"report agent"**
  that autonomously picks which deterministic analysis tools to call, in what order, and
  produces a structured explainable report.
- **Polito brief**: names it explicitly a **Multi-Agent System
  (MAS)** — a *decentralized* architecture with distinct autonomous **Cleaning Agents**
  (dedup/noise filtering) and **Analytic Agents** (KPIs/anomalies/trends) that
  collaborate, with an explicit ask to demonstrate agent communication/coordination and
  scalability advantages over a monolithic script.

These aren't factually incompatible, but they imply different levels of architectural
decentralization. A single-orchestrator-plus-tool-library design (as currently
implemented) fully satisfies the AROL deck's wording but may read as missing the
explicit "MAS" requirement if graded literally against project_quer3.pdf — consider
whether ingestion/cleaning and analytics should be restructured as separate
communicating agents rather than plain function calls.

Other minor divergences: data source (AROL: curated "data pools" provided directly;
Polito: pulled from Cloud into local persistence), machine name (AROL: generic; Polito:
named **Equatorque**), and deliverable format (see 8).

### Team decision (2026-08-14)

The team has decided to **prioritize the AROL deck framing as the primary target**
for this project: the single LLM "report agent" orchestrating deterministic tools
(section 3 Objective, section 8 "AROL deck version" deliverables). The Polito
brief's MAS framing (section 6, and the "Polito brief version" deliverables in
section 8) is kept below **for reference only** and is not the current
implementation target — it should not drive further architectural changes (e.g. no
need to split ingestion/cleaning and analytics into separate communicating agents)
unless the team revisits this decision. Nothing in sections 4, 5, 7, 10, or 11 is
affected by this — that content (data schema, status codes, core tasks, example
queries/outputs) comes from the AROL side and remains fully in scope.

## 3. Objective

Design and implement an Agentic AI / Multi-Agent application that:

1. Ingests and organizes telemetry datasets from AROL capping machines (small number of
   curated "data pools").
2. Provides a **BOT interface** (CLI, web, or lightweight UI) that generates analysis
   reports on demand (anomaly summaries, trends, correlations, basic KPIs), selecting
   analysis steps autonomously.
3. Produces repeatable, explainable outputs (reports + plots/tables), suitable for
   technical users in R&D/Service.

## 4. Data schema

Capping diagnostic data, wide format, one row per second:

```
timestamp, H01 Count, H01 AppTorque, H01 Status, H02 Count, H02 AppTorque, H02 Status, ..., H48 AppTorque, H48 Status
2026-05-20T02:26:12Z, 23553, 2.54, 0, 23499, 2.51, 0, ..., 2.48, 0
```

- Per-head **closure torque** and **closure status**, up to 48 heads.
- A closure event is detected by comparing a head's counter to its previous value
  (counter increments on real closure).

### Status codes

| Code | Reject? | Label | Description |
|---|---|---|---|
| 0 | NO | Closure OK | — |
| 2 | NO | No Load | — |
| 3 | YES | Slow Torque | Failing to reach the first torque threshold |
| 4 | NO | No Closure | — |
| 5 | YES | No Closure (reject) | Failing to reach the final torque (ClosureTorque) |
| 8 | NO | No InTorque | — |
| 9 | YES | No InTorque (reject) | Closure head raises before TimeInTorque elapsed |
| 16 | NO | No CapTurns | — |
| 17 | YES | No CapTurns (reject) | Cap closed but with fewer degrees than CapTurns |
| 32 | NO | Following Error | Tracking error between real and controlled position |
| 33 | YES | Following Error (reject) | — |
| 64 | NO | Bad Closure | — |
| 65 | YES | Bad Closure (reject) | ClosureTorque reached but cap still rotating when head raises |

Idle detection: a head is "idle" when it sustains status code 2 ("No Load") for a
sustained period (e.g. 300s).

## 5. Core tasks

**Data ingestion & normalization**
- Load one or more dataset pools (CSV/JSON/Parquet), normalize into a consistent
  internal schema.
- Validation checks: missing values, timestamp consistency, units metadata.
- Detect head closures via counter comparison against previous records.
- For each detected closure, collect torque + status.
- Compute capping speed (pieces/hour) via incremental average.
- Compute per-closure timestamp.

**Baseline analytics layer** (deterministic, callable as agent tools)
- Trend analysis (moving averages, drift detection) on torque values.
- Simple anomaly detection (thresholds, statistical deviations).
- Correlation checks among selected signals (e.g. head 1 vs head 5).
- Idle-state identification ("No Load" sustained per head).

**Agentic AI orchestration ("report agent")**
- Interpret a free-text user request (e.g. "Generate a weekly anomaly report for Line
  X", "Explain why downtime increased").
- Decide which tools to run, in which order.
- Produce a structured report: goal → data used → analyses executed → findings →
  confidence/limits → next checks.

**BOT interface** — choose one, prioritizing robustness/deployability:
- CLI tool (preferred for fast iteration): `report anomalies`, `report drift`,
  `report kpi`.
- Minimal web UI (optional) with report download.
- Local service exposing REST endpoints.

**Engineering quality & reproducibility**
- Configuration-driven datasets (no hard-coded paths).
- Logging, error handling, test cases on at least one dataset pool.
- Documented build/run instructions.

## 6. MAS-specific objectives (Polito brief — deprioritized per team decision, kept for reference)

- **Data Ingestion & Local Synchronization**: pull raw datasets from Cloud, manage a
  local persistence layer.
- **Agent-Based Data Cleaning**: "Cleaning Agents" filter noise, specifically the
  mismatch between polling frequency and the (slower) actual production cycle.
- **Deduplication & Logic Filtering**: rules to identify/remove redundant entries while
  preserving capping-process timestamp integrity.
- **Advanced Data Analytics**: "Analytic Agents" perform higher-level reasoning
  (performance KPIs, anomaly detection, trend analysis) on cleaned data.
- **Scalability & Autonomy**: demonstrate the agent-based approach handling increasing
  data volumes better than monolithic scripts.

## 7. Prerequisites / required background

- Strong programming autonomy (design, debug, deliver without step-by-step
  supervision).
- Python (or another systems-capable language) — scripting, packaging, CLI tools.
- Data handling: CSV/JSON parsing, timestamps, basic statistics.
- Basic software architecture: layers, interfaces, testability.
- Ability to read technical specs and reason about industrial signals
  (alarms/states/counters/diagnostics).
- Distributed systems basics: agent communication protocols, coordination models.
- Industrial IoT familiarity: PLC-generated data (capping torque, angle, success/fail
  flags).
- Basic SQL/NoSQL + Pandas/NumPy for local storage and manipulation.

## 8. Deliverables

**AROL deck version (primary target — see Team decision in section 2):**
- Source code repository (clean structure, reproducible run).
- Report templates (Markdown/HTML/PDF export).
- Sample generated reports.
- Technical documentation: architecture, data schema, analytics methods, agent
  decision flow.
- Demo: one end-to-end run loading a dataset pool and generating ≥2 report types.
- Short final presentation (10–15 slides).

**Polito brief version (reference only, not the current target):**
- Source files.
- A plain-ASCII **README** with compile/run instructions, execution parameters, dataset
  formats.
- A **DOCUMENTATION** file (Word/LaTeX/Markdown) with design choices and an
  experimental evaluation (tables/plots).
- A set of **OVERHEAD slides** for a 20-minute oral presentation.

## 9. Evaluation criteria

- Correctness and robustness of ingestion/normalization.
- Quality and usefulness of analytics outputs (signal handling, drift/anomaly
  evidence).
- Agentic orchestration quality (clear tool-use flow, explainable outputs, graceful
  failures).
- Software engineering quality (tests, structure, documentation, reproducibility).
- Demo clarity and technical communication.

## 10. Example queries the BOT should handle

**Basic exploration**: how many capping operations in the selected month; closures per
head; time range covered; missing/invalid torque values.

**Quality / success-rate**: % successful capping operations; failed count; success rate
per head; lowest-performing head.
> Example expected answer: *"92.4% of the capping operations resulted in a positive
> outcome over the analyzed period."*

**Torque analytics**: average closing torque for successful ops; torque distribution;
out-of-range values; successful vs failed torque comparison; head with highest torque
variability.

**Time-based / trend**: success rate evolution over time; daily breakdown; abnormal
failure-rate intervals; torque change over the month; time-of-day vs failure
correlation.

**Filtering / conditional**: only positive-outcome ops; failed ops below a torque
threshold; ops above X Nm; per-head filtered views; dedup-aware counts.

**Diagnostic / comparative**: which head behaves differently; unusual failure counts;
head-to-head comparison; which head contributes most to failures; torque-vs-success
correlation.

**Explanation-oriented (agentic)**: why success rate is lower on certain days; why a
head has more failures; summarize main process issues; which signals need closer
monitoring; generate a short quality report.

**Visualization-oriented**: torque-over-time plot for successful closures; torque
histogram; success-rate-per-head chart; failed closures over time; dashboard summary.

**Meta / system**: what preprocessing was applied; how duplicates were detected/removed;
cleaning assumptions; features used to classify a successful closure.

## 11. Expected output examples

**Overall process quality**
```
Total closure events analyzed: 1,248,320
Successful closures:           1,164,870
Failed closures:                   83,450
Overall success rate: 93.3%
```
> "After removing duplicated records and reconstructing individual closure events,
> 93.3% of the capping operations resulted in a successful outcome over the analyzed
> one-month period."

**Head-level performance** (table: Head ID, Total Closures, Successful, Success Rate)
> "Head 5 shows a significantly lower success rate compared to the others and may
> require further investigation."

**Torque statistics for successful closures**
```
Successful closure events analyzed: 1,164,870
Average torque: 2.41 Nm
Minimum torque: 1.85 Nm
Maximum torque: 3.12 Nm
Standard deviation: 0.22 Nm
```
> "The torque values show a stable distribution around the nominal operating range,
> suggesting correct overall mechanical behavior during successful closures."
