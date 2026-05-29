# Response to Reviewers — APEN-D-26-09220

**Manuscript:** Design-actionable cost–resilience thresholds for islanded battery–hydrogen microgrids: component drivers, diesel-support robustness, and dynamic feasibility
**Original title:** Cost-Resilience Thresholds for Battery-Hydrogen Hybrid Microgrids in Islanded Power Systems: An 8760-h Real-Weather Philippines Study

---

We thank the editor and the three reviewers for their detailed and constructive assessment. The revision substantially strengthens the paper along exactly the axes the reviewers identified. In summary, we have added four new analyses and one dynamic-feasibility study, all reproducible from the released code:

- a **continuous, finely resolved threshold contour** (diesel cost in 50 USD MWh⁻¹ steps, hydrogen CAPEX in 0.05 steps), replacing the original coarse three-point sensitivity (new Fig. 3, Table 3);
- a **cost-driver attribution** that identifies which design parameters move the threshold (new Fig. 4, Table 5);
- a **matched-backbone experiment** that isolates the contribution of the flexibility technology from that of the shared PV–battery backbone (new Fig. 5, Table 4);
- a **graded diesel-support robustness analysis** that relaxes the diesel-unavailability assumption across derating, fuel-budget, and start-up-delay cases (new Fig. 6);
- a **reduced-order frequency-response screen** (aggregated swing dynamics with droop and grid-forming virtual inertia) for all portfolios and the key islanded contingencies (new Fig. 7, Table 6, and a Supplementary parameter table).

We have also rewritten the introduction and literature review, made the cost formulation fully explicit, clarified the role of PV, and corrected the description of the input data (see Reviewer #3, point 4). Page/section/figure references below are to the revised manuscript. Reviewer comments are paraphrased in *italics*; our responses follow.

---

## Reviewer #1

**1.1 —** *The islanded system requires treatment of frequency stability, system dynamics (e.g. a state-space / swing representation), and the grid-forming reference; a purely energy-economic model is insufficient for an islanded power system.*

**Response.** We agree and have added a dedicated dynamic-feasibility analysis (new Section 3.6, Fig. 7, Table 6; method in Section 2, Eq. 10). We model the aggregated primary-frequency response with a swing equation,
d Δf/dt = (f₀ / 2 H_eq S_sys)[ΣδPᵢ − ΔP_dist − D_eq Δf], coupled to first-order droop/grid-forming dynamics τᵢ dδPᵢ/dt = −δPᵢ − Kᵢ Δf for each resource, with an explicit grid-forming reference assigned per portfolio (battery virtual-synchronous-machine for the all-renewable portfolios; diesel governor when on-line, battery on diesel loss for the diesel portfolio; battery plus fuel-cell droop for the hydrogen portfolio). The parameters and their sources are tabulated in the Supplementary. The screen evaluates a 10% load step and the loss-of-diesel contingency, reporting frequency nadir, instantaneous and 500 ms RoCoF, and the steady-state offset. The result is informative rather than merely confirmatory: under a load step all portfolios hold the nadir above 49 Hz, but the diesel–battery portfolio is dynamically weakest at precisely the diesel-trip contingency (500 ms RoCoF 5.9 Hz s⁻¹, nadir 45.9 Hz, requiring under-frequency load shedding although the grid-forming battery sustains the critical fraction), which is the same event at which Sections 3.4–3.5 find it energetically weakest. We have added the relevant grid-forming/frequency literature (\cite{liu2016comparison,shahgholian2025droop,chamorro2020innovative,olasoji2024review}). We are explicit (Section 2 and Section 4.4) that this is a reduced-order primary-response screen establishing feasibility and ranking contingencies, not a substitute for EMT simulation, secondary control, UFLS design, or protection coordination, which we identify as required next steps.

---

## Reviewer #2

**2.1 —** *The central message — hydrogen becomes attractive when diesel is expensive — is essentially obvious; the paper needs a less self-evident contribution.*

**Response.** We accept that the bare statement is unsurprising, and we have restructured the paper so that the contribution is the *structure behind* that statement, which is not obvious a priori (new Section 4.2). Specifically: (i) the threshold is governed not by hydrogen-chain cost or efficiency but by PV capital cost (Section 3.3) — a non-intuitive consequence of the portfolio's energy balance; (ii) the resilience advantage survives a *matched* PV–battery backbone, so it is intrinsic to the long-duration store rather than a by-product of larger sizing (Section 3.4); (iii) the diesel portfolio's resilience is far more fragile than perfect-availability or single-seed analysis suggests — a six-hour start-up delay erases worst-case survivability entirely, whereas a 50% derate or 12 h of fuel does not (Section 3.5); and (iv) the most dangerous frequency contingency for the diesel portfolio is the loss of the very asset providing its inertia (Section 3.6). These are design-actionable, non-obvious refinements that convert the intuition into engineering guidance.

**2.2 —** *Which design levers actually move the Pareto/cost–resilience frontier?*

**Response.** This is now answered directly by a cost-driver attribution (new Section 3.3, Fig. 4, Table 5). Varying each parameter across its plausible range, the crossover diesel cost is most sensitive to PV capital cost (span 148 USD MWh⁻¹), then hydrogen-tank, electrolyser, and fuel-cell cost (92, 66, 45), with battery-energy cost minor (11) and the electrolyser/fuel-cell efficiencies negligible (<1). The dominance of PV cost is structural: the hydrogen portfolio carries 14 MW of PV versus 2.8 MW for the diesel portfolio. The actionable conclusion is that PV-cost reduction, not electrolyser/fuel-cell improvement, is the most effective lever for hydrogen competitiveness.

**2.3 —** *The cost formulation should be stated objectively and explicitly.*

**Response.** Section 2 now gives the full linear-program objective (Eq. 1), the capital-recovery factor (Eq. 6, CRF = 0.0944 at i = 7%, L = 20 yr), and the total-annual-cost accounting (Eq. 7: annualised CAPEX + fixed O&M + fuel + carbon + variable O&M + unserved-energy penalty), with all unit costs in Table 1 and the levelised-cost definition stated. Nothing in the cost computation is left implicit.

**2.4 —** *The literature review is insufficient.*

**Response.** The introduction and a new positioning discussion (Section 4.3) have been rewritten around a literature matrix that maps prior work to four dimensions — continuous carbon-priced threshold, design-parameter attribution, technology isolation, and dynamic feasibility — making explicit that the individual techniques are established and that the contribution is their integration. We have added DOI-verified references spanning Philippine off-grid techno-economics \cite{castro2022techno,castro2022data,meschede2019transferability,pascasio2021comparative,ocon2019energy,bertheau2018resilient}, battery–hydrogen techno-economics \cite{alharbi2025comparative}, survivability/resilience methodology \cite{marqusee2021resilience,mishra2023microgrid}, and grid-forming/frequency control \cite{liu2016comparison,shahgholian2025droop,chamorro2020innovative,olasoji2024review}.

**2.5 —** *Clarify why PV is included and how it is sized in each portfolio.*

**Response.** Section 2.8 now states the PV in each portfolio, and Section 3.4 shows it is not arbitrary: the matched-backbone experiment demonstrates that the hydrogen portfolio is infeasible below 14 MW of PV because the 33.5%-efficient hydrogen round-trip cannot otherwise be balanced — the large PV is a physical requirement of the technology, not a modelling choice that biases the comparison. The matched-backbone design also places both portfolios on an identical PV–battery spine so that PV sizing cannot drive the resilience comparison.

---

## Reviewer #3

**3.1 —** *The threshold grid is too coarse to support the quantitative claims.*

**Response.** We have replaced the original three-point sensitivity with a finely resolved sweep (new Section 3.2, Fig. 3): delivered diesel cost over 100–1000 USD MWh⁻¹ in 50-step increments and a hydrogen-CAPEX multiplier over 0.30–1.20 in 0.05 increments, at a 150 USD tCO₂⁻¹ carbon price and a 48 h outage. The crossover is now reported as a continuous contour with a central value of 378 USD MWh⁻¹ (344 USD MWh⁻¹ when avoided unserved energy is valued at VOLL = 5000 USD MWh⁻¹), ranging 216–425 USD MWh⁻¹ across the CAPEX multiplier (Table 3). The fine sweep reproduces the original coarse points where they overlap.

**3.2 —** *Fixed component capacities may be driving the results.*

**Response.** This concern motivated the matched-backbone experiment (new Section 3.4, Fig. 5, Table 4). We place both portfolios on a common PV–battery backbone, varying PV (7/10/14 MW) and battery energy (8/12 MWh) identically and retaining only the distinguishing flexibility subsystem. Two findings follow: the hydrogen portfolio requires ≥14 MW PV to be viable at all (a physical, not arbitrary, requirement), and at an *identical* 14 MW/12 MWh backbone the diesel portfolio sheds critical load in the worst 48 h outage — zero worst-case survivable hours, worst-case CLSR 0.98 across ten seeds — while the hydrogen portfolio sustains the full 48 h (CLSR 1.0). Because the only difference at a matched backbone is the flexibility technology, the resilience advantage is attributable to the hydrogen store itself, not to fixed capacities.

**3.3 —** *The assumption that diesel is unavailable during an outage is too strong.*

**Response.** We have relaxed it across a graded set of diesel-support cases (new Section 3.5, Fig. 6). Under full unavailability (D0) the diesel portfolio's worst-case survivability is 0 h (worst-case CLSR 0.58 across ten seeds; the original single-seed 0.65 was optimistic). Restoring support closes the gap only above clear thresholds: the diesel portfolio matches the hydrogen portfolio's 48 h survivability only with ≥50% derating (D1) or ≥12 h of fuel (D2); critically, *any* start-up or delivery delay — even 6 h (D3) — returns worst-case survivability to 0 h. With diesel fully available but its fuel cost shocked (D4), the economic crossover is unchanged at 378 USD MWh⁻¹. Thus the hydrogen portfolio's value is specifically a hedge against degradation of diesel support — derating, fuel limits, or delivery delay — the characteristic failure modes during storms and logistics disruptions.

**3.4 —** *The "real-weather" study is not actually linked to the outage analysis (and the data description is unclear).*

**Response.** We have both clarified the data provenance and made the weather–outage link explicit. The solar resource is genuine NASA POWER hourly data (CERES SYN1deg all-sky surface shortwave irradiance and MERRA-2 2-m temperature) for calendar year 2025 at the grid cell 11.0°N, 123.0°E in the central Visayas; the PV capacity factor is derived from these measurements via a NOCT cell-temperature model (Eq. 11, annual mean CF 16.2%). The demand is a representative calibrated load archetype, which we now state plainly — the *weather* is real while the *load* is representative, an approach standard for islands lacking public hourly metered demand. We have removed any wording implying a measured load. The link to outages is now explicit: the 8760 h real-weather dispatch determines each portfolio's storage state entering an outage, and the outage simulation samples islanding start times across the real-weather year (worst-case across ten seeds and three durations), so the resilience metrics are conditioned on the measured solar resource rather than a stylised profile. We thank the reviewer — addressing this also let us identify and fix a stale configuration flag in the released code so that the repository description matches the real-weather dataset.

---

## Other changes
- Right-sized the hydrogen tank from 50,000 to 10,000 kg after verifying that resilience is invariant to tank size over 5,000–50,000 kg (CLSR = 1.0, full 48 h survivability); this removed capital equal to 47% of the hydrogen portfolio's CAPEX with no change in resilience or operating cost, lowering its LCOE from 610 to 381 USD MWh⁻¹ (Section 3.1).
- Title revised to reflect the design-actionable framing.
- Code, configuration, and data are archived (Zenodo DOI 10.5281/zenodo.19658748) and reproduce all figures and tables.

We believe the revision fully addresses the reviewers' concerns and hope it is now suitable for publication.

---

> **To finalise before submission:** insert reviewer verbatim text if the journal
> requires it; confirm final section/figure/table numbers against the typeset
> manuscript; confirm the Zenodo DOI resolves to the revised release; ensure the
> `\cite{}` keys match the merged `refs.bib`.
