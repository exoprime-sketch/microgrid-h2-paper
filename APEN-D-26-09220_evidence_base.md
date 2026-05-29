# APEN-D-26-09220 — Consolidated Evidence Base

**Paper:** Cost–Resilience(–Dynamic) Thresholds for Battery–Hydrogen Hybrid Microgrids in Islanded Power Systems (8760-h real-weather Philippines study)
**Status:** All simulations complete (H2-tank resize + E1, E2, E3, E4, E6). Ready for manuscript rewrite + response letter.
**Model:** Pyomo + HiGHS LP, 8760-h dispatch; reduced-order ODE for dynamics. Discount 0.07, life 20 yr, S_sys (peak load) 1.65 MW.

---

## 1. The unified thesis (paper spine)

> A battery–hydrogen portfolio is the defensible design for an islanded microgrid under **either** of two independently realistic conditions:
>
> **(a) Economic** — delivered diesel cost ≥ **377 USD/MWh** (≈ $3.77/L), within the real range for remote Philippine islands; **or**
>
> **(b) Resilience** — **any material degradation of diesel support during an outage** (derating below ~50%, fuel budget below ~12 h, or *any* delivery delay), which collapses the diesel–battery worst-case survivable duration to ~0 h — in both **energy** and **frequency-dynamic** terms — while the battery–hydrogen system holds full 48 h critical-load service through its structural long-duration H2 store.
>
> Both conditions are exactly the characteristics of remote-island / typhoon contingencies. The hydrogen portfolio's large PV (14 MW vs 2.8 MW) is a **physical requirement** of the H2 round-trip, not arbitrary oversizing, and PV-cost reduction is the single most powerful lever on hydrogen competitiveness.

---

## 2. Locked baseline (results/annual_costs.csv, 10,000 kg tank)

| Portfolio | Annual cost (USD/yr) | LCOE (USD/MWh) | Config notes |
|---|---|---|---|
| battery_only | 21,252,599 | 2,511 | no diesel/H2; dominated by unmet-load penalty |
| diesel_battery | 2,258,587 | 217 | PV 2.8 MW / 8 MWh / diesel 2.4 MW |
| battery_hydrogen | 3,965,969 | 381 | PV 14 MW / 12 MWh / elec 5 MW / FC 2.2 MW / **tank 10,000 kg** |

**H2-tank resize (central correction):** original 50,000 kg tank = 47% of CAPEX but only 51% utilised (LP never used >25,669 kg; outage-seed robustness identical CLSR=1.0 at all 5,000–50,000 kg). Resized to **10,000 kg** (76% headroom over the 5,669 kg max LP use). battery_hydrogen dropped from **6,353,827 USD/yr (LCOE 610.5) → 3,965,969 (381)** with **identical resilience** (CLSR=1.0, EENS=0, survivable 48 h) and unchanged variable O&M (28,390) — a pure capex-waste elimination, no operational change.

---

## 3. Evidence base by block

### E1 — Fine threshold contour `fig03` / `fig03b`, `crossover_diesel_cost.csv`
Diesel 100–1000 (step 50) × H2-CAPEX mult 0.30–1.20 (step 0.05), outage 48 h, carbon 150.

| H2 CAPEX mult | Crossover (pure) | Crossover (res-adj) |
|---|---|---|
| 0.30 | 215.6 | 180.6 |
| **1.00** | **376.9** | **341.8** |
| 1.20 | 422.9 | 387.9 |

Cross-validated against the original 3×3 heatmap (ΔC ≈ −0.2 at diesel 380 / mult 1.0). Crossover interior to [100,1000] for all 19 mult levels. **Replaces old Fig 2.**

### E2 — Cost-driver tornado `fig04`, `cost_driver_elasticity.csv`
Crossover-diesel-cost shift when each parameter is perturbed across a physical range (mult 1.0, carbon 150, outage 48). 42 LP solves (only the 2 efficiencies re-solve).

| Parameter | Span (USD/MWh) | Per-% elasticity |
|---|---|---|
| **PV capex** | **147.7** | **2.46** |
| H2 tank | 91.6 | 0.92 |
| Electrolyzer capex | 65.9 | 0.82 |
| Fuel cell capex | 45.1 | — |
| Battery energy capex | 11.0 | — |
| Fuel-cell efficiency | 0.9 | ~0 |
| Electrolyzer efficiency | 0.7 | ~0 |

**PV capex dominates** because hydrogen is intrinsically PV-intensive; efficiencies are negligible because the H2 subsystem is not the binding resilience constraint.

### E3 — Matched-backbone comparison `fig05`, `matched_backbone.csv`
Both portfolios on a common PV+battery spine (E/P = 6 h), 6 backbones, crossover via diesel sweep, resilience over 10 seeds.

| Backbone | Crossover | DB CLSR_min (surv) | BH CLSR_min (surv) | Δcost @ diesel 220 |
|---|---|---|---|---|
| B1 (7 MW / 8 MWh) | NaN | 0.842 | 0.974 | +28.1M |
| B4 (10 / 12) | NaN | 0.961 | **1.000** | +4.25M |
| B5 (14 / 8) | 316.6 | 0.885 | 1.000 | +0.32M |
| **B6 (14 / 12)** | 598.0 | **0.966 (1 h)** | **1.000 (48 h)** | +0.75M |

**Two key results:** (1) hydrogen needs **PV ≥ 14 MW** to be feasible (B1–B4 NaN crossover, huge unmet-load cost) — large PV is physical, not arbitrary. (2) At the **identical** 14 MW / 12 MWh backbone, diesel–battery survives only **1 h** of the worst 48-h outage while battery–hydrogen survives **48 h** — the resilience gap is **structural (H2 long-duration store), not PV sizing**.

### E4 — Diesel outage robustness `fig06`, `outage_robustness.csv`
Unmatched base portfolios; graded diesel-support cases; 10 seeds. (resilience.py extended additively, regression-guarded: reproduces original CLSR=0.643/EENS=45.7/surv=3 h at seed 2025.)

| Case | diesel–battery worst-case |
|---|---|
| D0 unavailable | surv **0 h**, CLSR_min 0.572 (worse than original single-seed 0.643 — honest) |
| D1 derate | ≥ **50%** → 48 h (25% → 0 h) |
| D2 fuel budget | ≥ **12 h** → 48 h (3 h → 10 h; 6 h → 28 h) |
| D3 delay | **any delay → 0 h** (even 6 h) |
| D4 fuel-cost shock | crossover unchanged at **376.9**; above 380 hydrogen is cheaper AND equally resilient |

### E6 — Reduced-order frequency screening `fig07`, `frequency_response_metrics.csv`, `dynamics_parameters.md`
Aggregate swing equation + first-order droop; explicit grid-forming source per portfolio. RoCoF formula includes S_sys (asserted ≤1% vs ODE). Settling relative to final value; droop offset reported; primary-response-only framing.

| Portfolio / case | nadir | RoCoF inst. | RoCoF 500 ms | verdict |
|---|---|---|---|---|
| diesel_battery / load step | 49.76 | 0.86 | 0.47 | PASS (both standards) |
| battery_only / load step | 49.71 | 1.88 | 0.42 | PASS (islanded) |
| battery_hydrogen / load step (op1) | 49.69 | 2.06 | 0.41 | marginal → VSM-tuning rec (H≥1.2 s → 1.37) |
| diesel_battery / **diesel trip** (op2) | 45.86 | **27.4** | **5.90** | secondary regime; **CritOK=T** (battery 1.5 ≥ crit 0.91 MW) |

**Finding:** all portfolios dynamically feasible in normal operation; diesel–battery is dynamically weakest **only** during the diesel-trip handover (same event as its E3/E4 energy weakness). battery–hydrogen has no diesel to lose. Large-disturbance steady states are secondary-control-dependent (AGC/UFLS/dispatch), explicitly framed.

---

## 4. Reviewer-response mapping

| Reviewer concern | Answered by |
|---|---|
| **#1** state-space / frequency stability / grid-forming reference | **E6**: reduced-order swing+droop screen with explicit grid-forming source per portfolio and mode; dynamics_parameters.md (Supplementary) |
| **#2** "H2-good-when-diesel-expensive is obvious"; which levers move the Pareto frontier; cost formulas; PV inclusion | **E1** (precise frontier), **E2** (component decomposition — PV dominant), **E3** (isolates true hydrogen value); objective cost formulas to be expanded in Methods; PV capacities moved to main text |
| **#3** threshold grid too coarse; fixed capacities drive results; diesel-unavailable too strong; weather not linked to outages | **E1** fine grid; **E3** matched backbone (capacity not driving the resilience result); **E4** diesel-assumption stress test; 8760-h real-weather dispatch feeds outage starting states |

---

## 5. Figure & table plan (manuscript)

**Figures:** fig01 architecture + grid-forming (to create) · fig02 base dispatch (refresh existing) · **fig03** threshold contour (E1, replaces old Fig 2) · fig03b res-adjusted contour (Supplementary) · **fig04** cost-driver tornado (E2) · **fig05** matched backbone (E3) · **fig06** outage robustness (E4) · **fig07** frequency response (E6).

**Tables:** portfolio capacities (move to main) · crossover table (E1) · cost-driver elasticity (E2) · matched-backbone (E3) · outage-robustness (E4) · frequency-response metrics (E6) · dynamics parameters (Supplementary).

---

## 6. Remaining work checklist

- [ ] **Manuscript rewrite** — title, abstract, intro reframe to design-actionable cost–resilience–dynamic thresholds; Methods (objective cost formulas: annualized CAPEX via CRF, fixed O&M, variable O&M, diesel, carbon, unserved; Eq 8–9 outage-set notation); Results around the 7 figures; Discussion (unified thesis); Conclusion.
- [ ] **Literature expansion** 21 → 35–50 refs, **all DOI-verified via Crossref** (never AI-generated citations); add literature matrix table.
- [ ] **Response-to-reviewers letter** — per comment: where changed / what simulation added / which figure-table reports it.
- [ ] **Supplementary** — fig03b, dynamics_parameters.md (fix "≈ 3–6 Hz/s"), symmetric ±30% tornado (optional, preempts asymmetric-range critique).
- [ ] **Submission package** — main_revised, supplementary_revised, response letter, cover letter, highlights, declaration, data-availability, reproducibility zip (Zenodo DOI 10.5281/zenodo.19658748).
