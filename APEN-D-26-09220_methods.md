# APEN-D-26-09220 — Methods (Section 2, revised draft)

> LaTeX-ready. Notation is self-consistent within this section. The cost
> formulation (§2.3) directly answers Reviewer #2's request for explicit
> objective formulas; the outage-set notation (§2.4, Eqs. for Ω, EENS, CLSR)
> answers Reviewer #3. **The LP objective and constraints in §2.2 reflect the
> standard form of the implemented model and must be verified line-for-line
> against `model/dispatch_model.py`** before final submission (see note at end).

---

## 2. Methods

We compare three fixed-architecture portfolios for an islanded microgrid: a PV–battery system (`battery_only`), a PV–diesel–battery system (`diesel_battery`), and a PV–battery–hydrogen system (`battery_hydrogen`). For each portfolio we (i) solve an 8760-h cost-optimal dispatch, (ii) accumulate an annualised total cost, (iii) evaluate critical-load resilience over a stochastic outage set, and (iv) screen primary-frequency dynamics with a reduced-order model. Sections 2.5–2.6 define the cost–resilience threshold, the matched-backbone construction, and the diesel-support robustness sweep that the Results build on.

### 2.1 Sets, variables, and parameters

Let $t \in \mathcal{T}=\{1,\dots,8760\}$ index the hours of one year, with time step $\Delta t = 1\,\mathrm{h}$. The hourly decision variables are the used PV power $p^{\mathrm{pv}}_t$, battery charge and discharge powers $p^{\mathrm{ch}}_t,\,p^{\mathrm{dis}}_t$ and state of charge $e_t$, diesel power $p^{\mathrm{dg}}_t$, fuel-cell power $p^{\mathrm{fc}}_t$, electrolyser power $p^{\mathrm{el}}_t$, hydrogen inventory $m_t$, and unserved load $u_t$ (all $\ge 0$). Fixed inputs are the demand $D_t$ and the available PV $\hat{p}^{\mathrm{pv}}_t$. Installed sizes are $\bar S^{\mathrm{pv}}$, battery power $\bar S^{\mathrm{bp}}$ and energy $\bar S^{\mathrm{be}}$, $\bar S^{\mathrm{dg}}$, $\bar S^{\mathrm{fc}}$, $\bar S^{\mathrm{el}}$, and tank $\bar S^{\mathrm{tk}}$ (kg). Round-trip parameters are battery charge/discharge efficiencies $\eta^{\mathrm{ch}},\eta^{\mathrm{dis}}$, electrolyser and fuel-cell LHV efficiencies $\eta^{\mathrm{el}},\eta^{\mathrm{fc}}$, and the hydrogen lower heating value $\mathrm{LHV}=33.3\,\mathrm{kWh\,kg^{-1}}$. Cost parameters are summarised in Table 1.

### 2.2 Optimal dispatch model

For fixed capacities, the hourly dispatch minimises annual operating cost,
$$
\min \; \sum_{t\in\mathcal{T}} \Big[ (c^{\mathrm{fuel}} + c^{\mathrm{co_2}}\varepsilon^{\mathrm{dg}})\,p^{\mathrm{dg}}_t + c^{\mathrm{thr}}\,(p^{\mathrm{ch}}_t + p^{\mathrm{dis}}_t) + c^{\mathrm{el}}\,p^{\mathrm{el}}_t + c^{\mathrm{fc}}\,p^{\mathrm{fc}}_t + c^{\mathrm{pen}}\,u_t \Big]\,\Delta t,
\tag{1}
$$
where $c^{\mathrm{fuel}}$ is the delivered diesel cost (USD MWh$^{-1}$ of electrical output), $\varepsilon^{\mathrm{dg}}=0.70$ t CO$_2$ MWh$^{-1}$ the diesel emission factor, $c^{\mathrm{co_2}}$ the carbon price, $c^{\mathrm{thr}}=1$ USD MWh$^{-1}$ a battery throughput (cycling) cost charged on both charge and discharge, $c^{\mathrm{el}}=2$ and $c^{\mathrm{fc}}=4$ USD MWh$^{-1}$ small electrolyser and fuel-cell variable-O\&M terms, and $c^{\mathrm{pen}}=10{,}000$ USD MWh$^{-1}$ a high unserved-energy penalty that makes load-shedding a last resort within the dispatch (a modelling device, distinct from the value of lost load used for resilience in §2.4). With $\Delta t=1\,\mathrm{h}$, each hourly power term equals its energy.

Subject to, for all $t$, PV allocation with explicit curtailment $p^{\mathrm{cu}}_t$ and the system power balance:
$$
p^{\mathrm{pv}}_t + p^{\mathrm{cu}}_t = \hat{p}^{\mathrm{pv}}_t = \bar S^{\mathrm{pv}}\,\gamma_t,
\tag{2}
$$
$$
p^{\mathrm{pv}}_t + p^{\mathrm{dis}}_t + p^{\mathrm{dg}}_t + p^{\mathrm{fc}}_t + u_t \;=\; D_t + p^{\mathrm{ch}}_t + p^{\mathrm{el}}_t,
\tag{3}
$$
where $\gamma_t\in[0,1]$ is the PV capacity factor. Storage dynamics use battery charge/discharge efficiencies $\eta^{\mathrm{ch}}=\eta^{\mathrm{dis}}=0.95$ and hydrogen conversion coefficients $\kappa^{\mathrm{el}}=10^{3}\eta^{\mathrm{el}}/\mathrm{LHV}=20.1$ kg MWh$^{-1}$ and $\kappa^{\mathrm{fc}}=10^{3}/(\eta^{\mathrm{fc}}\,\mathrm{LHV})=60.0$ kg MWh$^{-1}$:
$$
e_t = e_{t-1} + \eta^{\mathrm{ch}} p^{\mathrm{ch}}_t \Delta t - \tfrac{1}{\eta^{\mathrm{dis}}} p^{\mathrm{dis}}_t \Delta t, \qquad
m_t = m_{t-1} + \kappa^{\mathrm{el}} p^{\mathrm{el}}_t \Delta t - \kappa^{\mathrm{fc}} p^{\mathrm{fc}}_t \Delta t,
\tag{4--5}
$$
with bounds $0\le e_t\le\bar S^{\mathrm{be}}$, $0\le m_t\le\bar S^{\mathrm{tk}}$, and rated-power limits $p^{\mathrm{ch}}_t,p^{\mathrm{dis}}_t\le\bar S^{\mathrm{bp}}$, $p^{\mathrm{dg}}_t\le\bar S^{\mathrm{dg}}$, $p^{\mathrm{fc}}_t\le\bar S^{\mathrm{fc}}$, $p^{\mathrm{el}}_t\le\bar S^{\mathrm{el}}$. Both stores are initialised at 50% of capacity and constrained to return to that level at year-end ($e_{-1}=e_{8759}=0.5\,\bar S^{\mathrm{be}}$, $m_{-1}=m_{8759}=0.5\,\bar S^{\mathrm{tk}}$), giving an annually self-consistent cycle. The implied hydrogen round-trip efficiency is $\kappa^{\mathrm{el}}/\kappa^{\mathrm{fc}}=33.5\%$. The program is a linear program solved with HiGHS; capacities enter as fixed bounds, so the diesel cost and carbon price affect dispatch while capital costs do not.

### 2.3 Cost formulation and levelised cost

The reported annual cost adds annualised capital and fixed O&M to the optimised operating cost. Capital is annualised with the capital recovery factor
$$
\mathrm{CRF} = \frac{i\,(1+i)^{L}}{(1+i)^{L}-1}, \qquad i=0.07,\; L=20\,\mathrm{yr} \;\Rightarrow\; \mathrm{CRF}=0.0944.
\tag{6}
$$
With unit capital costs $c^{\mathrm{cap}}_k$ over components $k\in\mathcal{K}=\{\mathrm{pv,bp,be,dg,fc,el,tk}\}$, the total overnight capital is $\mathrm{CAPEX}=\sum_{k\in\mathcal{K}} c^{\mathrm{cap}}_k \bar S_k$ (MW sizes converted at $10^3$ kW MW$^{-1}$; the tank in kg directly), and the total annual cost is
$$
\mathrm{AC} \;=\;
\underbrace{\mathrm{CRF}\cdot\mathrm{CAPEX}}_{\text{annualised CAPEX}}
\;+\; \underbrace{\phi\cdot\mathrm{CAPEX}}_{\text{fixed O\&M}}
\;+\; \underbrace{c^{\mathrm{fuel}}E^{\mathrm{dg}}}_{\text{fuel}}
\;+\; \underbrace{c^{\mathrm{co_2}}\varepsilon^{\mathrm{dg}} E^{\mathrm{dg}}}_{\text{carbon}}
\;+\; \underbrace{c^{\mathrm{thr}}E^{\mathrm{thr}} + c^{\mathrm{el}}E^{\mathrm{el}} + c^{\mathrm{fc}}E^{\mathrm{fc}}}_{\text{variable O\&M}}
\;+\; \underbrace{c^{\mathrm{pen}}E^{\mathrm{uns}}}_{\text{unserved}} ,
\tag{7}
$$
where $\phi=0.025$ is the fixed-O\&M rate (fraction of CAPEX); $E^{\mathrm{dg}}=\sum_t p^{\mathrm{dg}}_t\Delta t$ is annual diesel energy; $E^{\mathrm{thr}}=\sum_t(p^{\mathrm{ch}}_t+p^{\mathrm{dis}}_t)\Delta t$ battery throughput; $E^{\mathrm{el}},E^{\mathrm{fc}}$ electrolyser and fuel-cell throughput; and $E^{\mathrm{uns}}=\sum_t u_t\Delta t$ unserved energy. The levelised cost of electricity is $\mathrm{LCOE} = \mathrm{AC}\,/\!\sum_t (D_t-u_t)\Delta t$, i.e. annual cost divided by annual served energy.

### 2.4 Resilience evaluation

Resilience is assessed on a stochastic set of islanding events. For an annual frequency $f^{\mathrm{out}}$ and a fixed duration $\Delta^{\mathrm{out}}$, the outage set is
$$
\Omega(s) = \big\{\,\omega_j = (\tau_j,\Delta^{\mathrm{out}}) \;:\; \tau_j \sim \mathcal{U}\{1,8760\},\; j=1,\dots,f^{\mathrm{out}} \,\big\},
\tag{8}
$$
with start hours drawn reproducibly from seed $s$. During each event the controllable sources serve the critical load $D^{\mathrm{crit}}_t = \alpha D_t$ (critical fraction $\alpha=0.55$) from the inventory carried into the event, using a priority dispatch (PV $\rightarrow$ battery $\rightarrow$ fuel cell $\rightarrow$ diesel, the last subject to §2.6). For a single event $\omega$ the energy not served and the served ratio are
$$
\mathrm{EENS}_\omega = \!\!\sum_{t\in\omega}\!\big(D^{\mathrm{crit}}_t - s_t\big)\Delta t, \qquad
\mathrm{CLSR}_\omega = \frac{\sum_{t\in\omega} s_t}{\sum_{t\in\omega} D^{\mathrm{crit}}_t},
\tag{9}
$$
where $s_t$ is the critical load actually served in hour $t$. The survivable duration $\Sigma_\omega$ is the number of contiguous hours from the event start before the first unserved hour. We report the worst case over the event set, $\mathrm{CLSR}_{\min}=\min_\omega \mathrm{CLSR}_\omega$, $\mathrm{EENS}_{\max}$, and $\Sigma_{\min}$, and—to monetise resilience—a value of lost load $\mathrm{VOLL}=5000$ USD MWh$^{-1}$ applied to expected EENS, giving the resilience-adjusted cost $\mathrm{AC}^{\mathrm{res}} = \mathrm{AC} + \mathrm{VOLL}\cdot\mathbb{E}_\Omega[\mathrm{EENS}]$. The base case uses $f^{\mathrm{out}}=4\,\mathrm{yr^{-1}}$, $\Delta^{\mathrm{out}}=48\,\mathrm{h}$; worst-case statistics are taken over ten seeds $s\in\{1,\dots,10\}$ unless stated.

### 2.5 Cost–resilience threshold and matched backbone

The economic comparison is summarised by the cost gap $\Delta C(c^{\mathrm{fuel}},\mu) = \mathrm{AC}_{\mathrm{BH}}(\mu) - \mathrm{AC}_{\mathrm{DB}}(c^{\mathrm{fuel}})$, where $\mu$ scales the hydrogen-subsystem capital costs (electrolyser, fuel cell, tank) and $c^{\mathrm{fuel}}$ is the delivered diesel cost. The **economic crossover** $c^{\star}(\mu)$ solves $\Delta C(c^{\star},\mu)=0$; the resilience-adjusted crossover uses $\Delta C^{\mathrm{res}} = \Delta C + \mathrm{VOLL}\,(\mathbb{E}[\mathrm{EENS}_{\mathrm{BH}}]-\mathbb{E}[\mathrm{EENS}_{\mathrm{DB}}])$. To separate the storage technology from the capacity it induces, the **matched-backbone** comparison assigns both portfolios a common PV size $\bar S^{\mathrm{pv}}$ and battery energy $\bar S^{\mathrm{be}}$ (battery power fixed at an energy-to-power ratio of 6 h), differing only in the flexibility subsystem (diesel for `diesel_battery`; electrolyser, fuel cell and tank for `battery_hydrogen`). Comparing the two on an identical backbone isolates the contribution of the flexibility technology to cost and resilience.

### 2.6 Diesel-support robustness

The base resilience case assumes diesel is unavailable during islanding. To test the sensitivity of the verdict to this assumption, the diesel contribution within an event is parameterised by a derating fraction $\delta\in(0,1]$, a fuel budget $B$ (hours at rated power), and a start delay $h_{\mathrm d}$, giving an effective deliverable power $\delta\,\bar S^{\mathrm{dg}}$ available only for $t\ge \tau+h_{\mathrm d}$ and only while cumulative diesel energy is below $B\,\bar S^{\mathrm{dg}}$. The cases are: D0 unavailable; D1 $\delta\in\{0.25,0.5,0.75\}$; D2 $B\in\{3,6,12,24\}\,\mathrm{h}$; D3 $h_{\mathrm d}\in\{6,12,24\}\,\mathrm{h}$; and D4 a delivered-fuel-cost shock applied to the annual economics. The hydrogen portfolio carries no diesel and is therefore the invariant reference.

### 2.7 Reduced-order frequency-stability screen

To confirm dynamic feasibility, primary frequency response is screened with an aggregate swing equation and first-order droop on each online source. With deviation $\Delta f$ from the nominal $f_0=50\,\mathrm{Hz}$ and source-power deviations $\delta P_i$,
$$
\frac{\mathrm d \Delta f}{\mathrm d t} = \frac{f_0}{2\,H_{\mathrm{eq}}\,S_{\mathrm{sys}}}\Big[\textstyle\sum_i \delta P_i - \Delta P_{\mathrm{dist}}(t) - D_{\mathrm{eq}}\Delta f\Big], \qquad
\tau_i\frac{\mathrm d \delta P_i}{\mathrm d t} = -\delta P_i - K_i\,\Delta f,
\tag{10}
$$
with system base $S_{\mathrm{sys}}=1.65\,\mathrm{MW}$ (peak load) and equivalent inertia $H_{\mathrm{eq}}=H_{\mathrm{gf}}S_{\mathrm{gf}}/S_{\mathrm{sys}}$ contributed by the grid-forming source. Each portfolio is assigned an explicit grid-forming source—battery virtual synchronous machine for `battery_only` and `battery_hydrogen`, diesel synchronous generator in normal operation for `diesel_battery` with battery hand-over during a diesel trip—directly reflecting that an islanded system's frequency reference is a grid-forming source rather than an external grid. Disturbances are a 10% load step, a 50% PV ramp, and a diesel-trip hand-over. Metrics are the frequency nadir, the instantaneous and 500-ms RoCoF, the primary droop offset $\Delta f(\infty)$, and the settling time relative to $\Delta f(\infty)$; screening thresholds are nadir $\ge 49.0$ Hz and $|\mathrm{RoCoF}|<2.0\,\mathrm{Hz\,s^{-1}}$ (islanded; a 1.0 Hz s$^{-1}$ mainland value is flagged for reference). The model represents primary response only; sustained rebalancing after a large disturbance is provided by secondary control, under-frequency load shedding, and hourly dispatch, which are outside the screen. Parameter values and citations are listed in the Supplementary (dynamics_parameters).

### 2.8 Data and case study

The case study is a representative small Philippine off-grid island with a peak demand of 1.65 MW—the scale of operational island microgrids such as the Sabang (Palawan) PV–battery–diesel system [cite SREC] and typical of the country's several hundred NPC-SPUG off-grid islands [cite Ocon et al.]. The **solar resource is real measurement-derived data**: NASA POWER hourly all-sky surface shortwave downward irradiance (CERES SYN1deg) and 2-m air temperature (MERRA-2) for calendar year 2025 at the grid cell centred on 11.0°N, 123.0°E in the central Visayas. The PV capacity factor is obtained from the measured irradiance $G_t$ (W m$^{-2}$) and air temperature $T^{\mathrm{air}}_t$ via a nominal-operating-cell-temperature (NOCT) model,
$$
T^{\mathrm{cell}}_t = T^{\mathrm{air}}_t + 0.0256\,G_t, \qquad
\gamma_t = \mathrm{clip}\!\Big[\tfrac{G_t}{1000}\,\eta_{\mathrm d}\,\big(1+\beta\,(T^{\mathrm{cell}}_t-25)\big),\,0,\,1\Big],
\tag{11}
$$
with system derate $\eta_{\mathrm d}=0.82$, temperature coefficient $\beta=-0.004\,^{\circ}\mathrm{C}^{-1}$, and the cell-temperature coefficient $0.0256$ corresponding to NOCT $\approx 40.5\,^{\circ}\mathrm{C}$; this yields an annual mean capacity factor of 16.2%, consistent with fixed-tilt PV at this tropical latitude. The hourly demand is a representative load profile calibrated to a 1.65 MW peak and a 0.72 load factor, with morning, evening, and commercial peaks, weekend reduction, and tropical-tourism seasonality; the weather is real while the load is a representative archetype, an approach standard for islands lacking public hourly metered demand. Base global parameters are $i=0.07$, $L=20$ yr (CRF $=0.0944$), $\varepsilon^{\mathrm{dg}}=0.70$ t CO$_2$ MWh$^{-1}$, $\alpha=0.55$, $\eta^{\mathrm{el}}=0.67$, $\eta^{\mathrm{fc}}=0.50$, $\eta^{\mathrm{ch}}=\eta^{\mathrm{dis}}=0.95$, $c^{\mathrm{pen}}=10{,}000$ and $\mathrm{VOLL}=5000$ USD MWh$^{-1}$. The base carbon price is $c^{\mathrm{co_2}}=0$; the threshold analysis sweeps it with $150$ USD t$^{-1}$ as the central value (Results). Because only the diesel portfolio emits, the carbon price affects the `diesel_battery` cost and hence the crossover, while the `battery_only` and `battery_hydrogen` costs are carbon-independent. Unit costs are in Table 1. After the hydrogen-tank right-sizing described in Results, the portfolios are sized as: `battery_only` (PV 7 MW / battery 2.2 MW / 24 MWh), `diesel_battery` (PV 2.8 MW / 1.5 MW / 8 MWh / diesel 2.4 MW), and `battery_hydrogen` (PV 14 MW / 2.0 MW / 12 MWh / electrolyser 5 MW / fuel cell 2.2 MW / tank 10,000 kg).

---

## Table 1 — Techno-economic parameters (confirmed from configs/scenarios.json)

| Component / parameter | Value | Notes |
|---|---|---|
| PV capital | 1200 USD/kW | |
| Battery power capital | 300 USD/kW | |
| Battery energy capital | 250 USD/kWh | |
| Diesel genset capital | 450 USD/kW | |
| Electrolyser capital | 900 USD/kW | |
| Fuel cell capital | 1400 USD/kW | |
| Hydrogen tank capital | 500 USD/kg | |
| Fixed O&M rate $\phi$ | 0.025 of CAPEX/yr | flat fraction of total CAPEX |
| Battery throughput $c^{\mathrm{thr}}$ | 1.0 USD/MWh | charged on charge + discharge |
| Electrolyser variable $c^{\mathrm{el}}$ | 2.0 USD/MWh | |
| Fuel cell variable $c^{\mathrm{fc}}$ | 4.0 USD/MWh | |
| Diesel fuel (base) $c^{\mathrm{fuel}}$ | 220 USD/MWh | delivered; swept in Results |
| Carbon price (base) $c^{\mathrm{co_2}}$ | 0 USD/tCO₂ | central sweep value 150 |
| Diesel emission factor $\varepsilon^{\mathrm{dg}}$ | 0.70 tCO₂/MWh | |
| Battery charge/discharge eff. | 0.95 / 0.95 | |
| Electrolyser / fuel-cell eff. (LHV) | 0.67 / 0.50 | round-trip 33.5% |
| Hydrogen LHV | 33.33 kWh/kg | |
| Initial SOC / H₂ inventory | 0.5 of capacity | cyclic to same |
| Unserved penalty $c^{\mathrm{pen}}$ | 10,000 USD/MWh | LP device |
| Value of lost load (resilience) | 5000 USD/MWh | |
| Discount rate / life | 0.07 / 20 yr | CRF = 0.0944 |

---

## ✓ Verified against dispatch_model.py + scenarios.json

Eqs. (1)–(7) and Table 1 now match the implemented model line-for-line:
objective (1) matches `objective_rule` (carbon folded into the diesel term;
throughput on charge+discharge; electrolyser/fuel-cell variable terms;
penalty); (2) matches `pv_allocation_rule` (explicit curtailment); (3) matches
`power_balance_rule`; (4)–(5) match `battery_soc_rule` / `h2_inventory_rule`
with 50% initial inventory and the `*_cyclic` end constraints; (7) matches
`calculate_summary` (fixed O&M = 0.025·CAPEX; variable O&M = throughput +
electrolyser + fuel-cell). No reserve, ramp, or minimum-load constraints exist
in the model — correctly omitted here.

## ✓ Weather-data provenance — RESOLVED (no re-run needed)

Verified against `data/external/nasa_power_philippines_2025.csv` and the active
`data/philippines_offgrid_8760.csv`: the solar resource is **real NASA POWER
data** (CERES SYN1deg irradiance + MERRA-2 temperature), hourly, UTC, calendar
year 2025, for the grid cell at **11.0°N, 123.0°E (central Visayas)**. The CF
formula (Eq. 11) reconstructs the stored `pv_capacity_factor` bitwise
(max diff 0.0). Annual mean CF = 16.2% (physically realistic). The
`weather.source = "synthetic"` flag in `scenarios.json` is a **stale, unused
documentation default** — no execution script reads it; `run_scenarios.py` and
`run_sensitivity.py` read the CSV directly. The "real-weather" claim is
therefore legitimate for the *weather*; the *load* is a representative
calibrated archetype, now described as such. **All E1–E6 results stand; no
re-run is required.**

**Location:** data are NOT for Sabang/Palawan but for the central-Visayas grid
cell 11.0°N, 123.0°E. Sabang/SREC is cited only as a real operational example
motivating the `diesel_battery` archetype, not as the data source. The
manuscript names the actual cell.

## Reproducibility mitigations (results-neutral; recommended before archiving)
1. In `scripts/prepare_case_study_data.py`, prevent a silent overwrite of the
   real CSV: require `--weather-file` (error out if absent) or default it to
   `data/external/nasa_power_philippines_2025.csv`. Currently, running it
   without the flag regenerates synthetic PV and overwrites the canonical file.
2. Correct the stale `scenarios.json` note (`weather.source`/case note) to state
   that the canonical dataset is real NASA POWER 2025 for 11.0°N, 123.0°E, so
   the repo description matches the artifact.
These touch only metadata / a data-prep guard, not the model or any result.

## Open confirmation (minor)
- Baseline `annual_costs.csv` (reproduction-guard values, e.g. diesel_battery
  2,258,587) are at carbon = 0; the headline crossover (377) is at carbon = 150.
  Decide whether to report baseline costs at carbon 0 or 150 for internal
  consistency, and state it once in Results.
