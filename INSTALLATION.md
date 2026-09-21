# Installation & Setup

## Prerequisites

- Python 3.10+ (tested on 3.11 and 3.14)
- The raw AROL telemetry CSV files (not included in this repository -
  see "Data" below)

An API key is already configured in `config/config.yaml` - no
additional setup needed to run the system.

## 1. Clone the repository

```powershell
git clone https://github.com/<org>/project-bottle.git
cd project-bottle
```

## 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script with an execution-policy
error, run this once (current terminal session only, not a permanent
system change):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 3. Install dependencies

```powershell
pip install -r requirements.txt
```

## 4. Add the data pool

Place the raw telemetry CSV files (one per machine per day, named
`telemetry_<machine_id>_<date>.csv`) into the `data/` folder. This
folder is gitignored - the repository does not include the raw dataset.

## 5. Run

```powershell
python -m src.cli report kpi
```

The first run processes the full raw dataset and builds a local cache
(`data/.cache/`) - this can take several minutes depending on data pool
size. Subsequent runs reuse the cache and complete in a few seconds,
unless new or changed files are detected in `data/`.

Other ways to run the system:

```powershell
python -m src.cli ask "which head has the most problems and why?"
python -m src.cli report anomalies
python -m src.cli report drift
python -m src.cli chat
```

## 6. Run the test suite

```powershell
pytest tests/
```

Tests run against small synthetic samples and do not require the real
data pool to be present.

## Troubleshooting

**`ModuleNotFoundError` for an installed package** - confirm the
virtual environment is actually active (`(.venv)` should appear at the
start of your terminal prompt); if not, re-run step 2's activation
command.

**`No data found` message** - confirm raw CSV files are present in
`data/` and match the expected filename pattern.
