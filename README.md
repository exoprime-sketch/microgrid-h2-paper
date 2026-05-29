# Island Microgrid Hydrogen Study — Applied Energy Revision

Reproducible code and data for the Applied Energy resubmission
**APEN-D-26-09220** comparing battery--hydrogen against PV--diesel--battery
portfolios in a Philippine off-grid island. The analysis covers cost thresholds,
component-level cost drivers, matched-backbone resilience, diesel-support
robustness, and reduced-order frequency stability.

**Portfolios modelled:**
- PV + battery (battery-only reference)
- PV + diesel + battery
- PV + battery + hydrogen (10,000 kg H₂ tank)

The dispatch model is a linear Pyomo optimisation solved with HiGHS (8760-h,
fixed-capacity, real NASA POWER weather, calibrated load archetype in local
time UTC+8).

## Manuscript

**The current submission-ready manuscript is `main_revised.tex`.**
Compile with:

```powershell
pdflatex -interaction=nonstopmode main_revised.tex
bibtex main_revised
pdflatex -interaction=nonstopmode main_revised.tex
pdflatex -interaction=nonstopmode main_revised.tex
```

Bibliography: `refs.bib` + `refs_additions.bib`.

## Project Layout

```text
configs/                Scenario, cost, resilience, and sensitivity assumptions
configs/cases/          ASEAN case-study metadata and load/weather settings
data/                   Prepared 8760-hour model inputs (NASA POWER weather, UTC+8 load)
data/external/          NASA POWER or ERA5 hourly weather CSV files
figures/                Publication figures fig02–fig07 (PDF + PNG)
model/                  Pyomo dispatch, load archetype, weather, resilience, dynamics
results/                Dispatch, summary, resilience, sensitivity, and analysis CSVs
scripts/                Reproducible run_*.py and plot_*.py workflows
```

## Reproduction (Windows PowerShell)

```powershell
# 1. Install dependencies
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2. Prepare case-study data (NASA POWER weather + UTC+8 load archetype)
.\.venv\Scripts\python scripts\prepare_case_study_data.py

# 3. Base scenarios (LP dispatch)
.\.venv\Scripts\python scripts\run_scenarios.py

# 4. E1–E4 analyses
.\.venv\Scripts\python scripts\run_fine_sweep.py        # E1 threshold contour
.\.venv\Scripts\python scripts\run_cost_driver.py       # E2 tornado
.\.venv\Scripts\python scripts\run_matched_backbone.py  # E3 backbone
.\.venv\Scripts\python scripts\run_outage_robustness.py # E4 robustness
.\.venv\Scripts\python scripts\run_dynamics.py          # E6 frequency screen

# 5. Figures
.\.venv\Scripts\python scripts\plot_base_dispatch.py
.\.venv\Scripts\python scripts\plot_fine_sweep.py
.\.venv\Scripts\python scripts\plot_cost_driver.py
.\.venv\Scripts\python scripts\plot_matched_backbone.py
.\.venv\Scripts\python scripts\plot_outage_robustness.py
.\.venv\Scripts\python scripts\plot_dynamics.py
```

macOS/Linux: replace `.\.venv\Scripts\python` with `./.venv/bin/python`.

## Philippines Case-Study Data

The canonical dataset is `data/philippines_offgrid_8760.csv` — 8760 hourly rows
with real NASA POWER irradiance (11.0 N, 123.0 E, 2025) and a calibrated
synthetic load archetype. The load diurnal shape is anchored to **local time
UTC+8** (evening peak at local 20:00) while timestamps remain in UTC for
alignment with the weather data.

To regenerate from the NASA POWER source file:

```powershell
.\.venv\Scripts\python scripts\prepare_case_study_data.py `
  --case-config configs\cases\philippines_offgrid.json `
  --weather-file data\external\nasa_power_philippines_2025.csv `
  --weather-format nasa-power `
  --output data\philippines_offgrid_8760.csv
```

## Weather File Columns

- NASA POWER hourly CSV: `YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN`; optional `T2M`.
- ERA5 hourly CSV export: a time column plus `ssrd` or
  `surface_solar_radiation_downwards`; optional `t2m`.
- Generic hourly CSV: `timestamp` plus `ghi_w_per_m2` or `pv_capacity_factor`.

ERA5 NetCDF/GRIB files must be exported to CSV before use.

## Key Results (post-revision)

| Metric | Value |
|---|---|
| Economic crossover (μ=1, carbon=150 USD/tCO₂) | 378 USD/MWh delivered diesel |
| Dominant cost driver | PV CAPEX (span 148 USD/MWh) |
| H₂ tank right-sized to | 10,000 kg (max LP utilisation 5,595 kg) |
| DB worst-case survivability (matched backbone, all sizes) | 0 h |
| BH worst-case survivability (14 MW PV backbone) | 48 h (CLSR 1.0) |
| D0 (no diesel) BH CLSR_min | 1.000 |
| Diesel-trip 500 ms RoCoF | 5.91 Hz/s (secondary control needed) |

## Resilience Analysis

The resilience post-processor evaluates 4 random outage events per year
(48 h duration, 10 seeds) and reports LPSP, EENS, critical-load served ratio
(CLSR), and minimum/mean survivable outage duration. Diesel is unavailable
during outages in the base case (D0).

## Model Notes

Fixed-capacity operations model: technology sizes are set in
`configs/scenarios.json`, then hourly dispatch is optimised to minimise annual
cost + unmet-load penalty. Cyclic end-of-year SOC and H₂ inventory constraints
prevent artificial drawdown.

Sensitivity sweeps reuse dispatch results when only CAPEX, carbon price, or
outage duration changes (no re-solve needed), keeping the 19×19 E1 sweep
practical on a local machine.
