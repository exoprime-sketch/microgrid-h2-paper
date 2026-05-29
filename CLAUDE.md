# Project context

This repository is the codebase for an Applied Energy resubmission on
battery-hydrogen islanded microgrids (manuscript APEN-D-26-09220,
rejected with major revisions). The original 50,000 kg H2 tank base case
has been replaced with a 10,000 kg tank because the LP-revealed maximum
utilization is only 5,669 kg (56.7%) and resilience screening confirms
CLSR=1.0 robustness across 50 outage seeds and 48/72/96 h durations
even at 5,000 kg. The 10,000 kg choice gives a 76% headroom over
maximum observed utilization.

# Reproduction (Windows PowerShell)

.\.venv\Scripts\python scripts\run_scenarios.py
.\.venv\Scripts\python scripts\run_sensitivity.py
.\.venv\Scripts\python scripts\plot_results.py

# Locked new-baseline values in results\annual_costs.csv

battery_only       21,252,599 USD/yr   LCOE 2,511 USD/MWh
diesel_battery      2,258,587 USD/yr   LCOE   217 USD/MWh
battery_hydrogen    3,965,969 USD/yr   LCOE   381 USD/MWh   (10,000 kg tank)

These must not change unless intentionally redesigned. Always verify by
reading results\annual_costs.csv after any rerun.

# Coding conventions

- LP: Pyomo + appsi_highs solver, fixed-capacity LP
- Add new scripts as scripts/run_<name>.py mirroring run_sensitivity.py
- Add new model modules under model/ - do NOT modify dispatch_model.py
  unless absolutely necessary
- Result CSVs to results/, figures to figures/, configs to configs/
- All CSV columns in snake_case
- Save JSON files without BOM (Python json.dump with encoding='utf-8' is
  fine; PowerShell Set-Content -Encoding UTF8 adds BOM and breaks json.load)

# Tasks in priority order

1. E1 fine threshold contour: diesel 100-1000 step 50, H2 mult 0.30-1.20
   step 0.05, at outage=48h carbon=150 USD/tCO2. Output:
   results/sensitivity_fine.csv and figures/fig03_threshold_contours.pdf
2. E2 cost-driver decomposition: H2 tank cost, electrolyzer capex,
   fuel cell capex, electrolyzer efficiency, fuel cell efficiency, PV
   capex each varied one-at-a-time +/-50%, measure crossover diesel cost
   shift. Output: results/cost_driver_elasticity.csv and
   figures/fig04_cost_driver_tornado.pdf
3. E4 diesel outage robustness: D0 (unavailable, current), D1 (derated
   25/50/75%), D2 (limited fuel 3/6/12/24 h equivalent), D3 (delayed
   support 6/12/24 h), D4 (available with fuel-cost shock 380-1000
   USD/MWh). Output: results/outage_robustness.csv and
   figures/fig06_outage_robustness.pdf
4. E6 reduced-order frequency stability screening: aggregate swing
   equation + first-order droop on battery/FC/diesel converters.
   Disturbances: 10% load step, 50% PV ramp drop in 1-5 s, source switch
   transient. Output: results/frequency_response_metrics.csv and
   figures/fig07_frequency_response.pdf, new module model/dynamics.py
5. Manuscript rewrite (intro reframe, methods expansion, results with
   new figures, discussion of frontier shift drivers, literature matrix
   extension to 35-50 refs).

# Things to NOT do

- Do NOT modify model/dispatch_model.py unless absolutely necessary
- Do NOT change configs/scenarios.json base values (H2 tank stays 10,000 kg)
- Do NOT invent citations - all references must be DOI-verified
- Always check Get-Content results\annual_costs.csv before claiming progress
