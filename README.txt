AROL TELEMETRY AGENT
====================

Agentic AI application for ingesting, normalizing, and analyzing AROL
Equatorque capping-machine telemetry (torque/closure diagnostics), with a
natural-language "report agent" on top of a library of deterministic
analysis tools.

NOTE: the current dataset covers a single machine. machine_id is carried
through the ingestion and the normalised readings for provenance/extensibility,
but the fnal closure analysis operate at head level only.

NOTE: the supplied telemetry dataset is treated as the already locally synchronised dataset. No cloud endpoint 
or storage interface was supplied, so the implementation starts from the local CSV dataset.

PROJECT STRUCTURE
------------------
config/config.yaml       All paths, thresholds, status codes, and the LLM
                          model name. Nothing in src/ is hard-coded.
data/                     Place raw data pool CSV files here.
data/.cache/              SQLite DB + ingestion manifest + normalised Parquet readings (auto-created).

src/ingestion/            Person A
  loader.py               Loads raw wide-format CSV data pool files.
  normalizer.py           Reshapes wide -> long, validates.
  db.py                   SQLite persistence (raw_telemetry,
                           closures) + ZSTD Parquet persistence (readings) + manifest-based freshness check.

src/closure_detection/    Person A
  detector.py              Closure/counter-advance detection, status
                           classification, per-head and machine-wide idle-period detection.

src/analytics/            Person B
  kpi.py                   success_rate, success_rate_per_head,
                           torque_stats, capping_speed_incremental
  trend.py                 moving_average, detect_drift
  anomaly.py                zscore_anomalies
  correlation.py            head_torque_correlation

src/agent/                 Person C
  tools.py                  Tool schemas (sent to the LLM) + the mapping
                            back to Person B's real functions.
  orchestrator.py            The tool-calling loop against the Anthropic API.

src/reporting/
  report_builder.py          Structured report dataclass (used for the
                             canned report path).

src/cli.py                  CLI entry point (ask / report commands).
tests/                       Unit tests, run against small synthetic samples.

HOW TO RUN
----------
1. create and activate a virtual environment:

   Windows PowerShell:
     python -m venv venv
     .\venv\Scripts\Activate.ps1

   Linux/macOS:
     python3 -m venv venv && source venv/bin/activate

2. pip install -r requirements.txt

3. set the Anthropic API key:

   Windows PowerShell:
     $env:ANTHROPIC_API_KEY="sk-ant-..."

   Linux/macOS:
     export ANTHROPIC_API_KEY="sk-ant-..."

4. Edit config/config.yaml if your data pool folder differs from data/.

5. Place raw telemetry_*.csv files in data/.

6. Run:
     python -m src.cli ask "What is the average closing torque for successful closures?"
     python -m src.cli report kpi
     python -m src.cli report anomalies
     python -m src.cli report drift

7. Tests: pytest --confcutdir=. tests/ -q

DATASET FORMAT
---------------
Each raw file: telemetry_<machine_id>_<date>.csv, wide format, one row per
second:
    timestamp, H01 Count, H01 AppTorque, H01 Status, H02 Count, ...
Reshaped internally to:
    timestamp, machine_id, head_id, count, app_torque, status, source_file
then, after counter-advance and status classification, to the final
closures table:
    timestamp, head_id, count, app_torque, status, count_increment,
    time_since_prev_seconds, status_label, is_reject
