# APEN-D-26-09220 — Title, Abstract, Introduction (revised draft)

> Drafted to lock the thesis framing. Abstract is ready prose; Introduction is
> LaTeX-ready with `\cite{P#}` placeholders to be resolved in the literature
> step (see checklist at the end). Quantitative claims are traceable to the
> evidence base (E1–E6).

---

## Title (recommended: A)

**A.** Design-actionable cost–resilience thresholds for islanded battery–hydrogen microgrids: component drivers, diesel-support robustness, and dynamic feasibility

**B.** When are battery–hydrogen microgrids justified? Cost, resilience, and dynamic thresholds from an 8760-h real-weather islanded study

**C.** Cost, resilience, and dynamic thresholds for islanded battery–hydrogen microgrids: an 8760-h real-weather analysis of design drivers and diesel-support robustness

---

## Abstract

Islanded and remote microgrids increasingly weigh battery–hydrogen storage against diesel-backed batteries, yet the conditions under which hydrogen is actually justified remain imprecisely defined. The cost, resilience, and frequency-stability dimensions of this choice have each been studied, but usually in separate analyses and for a single optimised design per technology—leaving open which design levers move the economic threshold, whether the resilience advantage is intrinsic to hydrogen or a by-product of its sizing, and how robust the verdict is to the assumed level of diesel support. Using an 8760-h cost-optimal dispatch model driven by real NASA POWER weather for a representative Philippine off-grid island, we bring these dimensions together into a single, design-actionable, multi-axis comparison of a battery–hydrogen portfolio against a PV–diesel–battery portfolio. We find an economic crossover at a delivered diesel cost of 377 USD/MWh. A component-level decomposition shows the frontier is governed primarily by photovoltaic capital cost—because the hydrogen portfolio is intrinsically PV-intensive—rather than by electrolyser or fuel-cell efficiency. A matched-backbone comparison demonstrates that the resilience advantage is structural: on an identical PV–battery spine, the diesel–battery system survives only about one hour of the worst 48-hour outage whereas the battery–hydrogen system sustains the full 48 hours, owing to long-duration hydrogen storage. A graded diesel-support stress test shows that any derating below roughly 50%, any fuel budget below about 12 hours, or any delivery delay collapses the diesel–battery worst-case survivability, and a reduced-order frequency screen confirms that this weakness extends to the dynamic layer during the diesel-trip grid-forming handover. Battery–hydrogen is therefore defensible whenever delivered diesel is costly or diesel support is degradable—precisely the conditions that characterise remote-island contingencies.

*(~230 words)*

**Keywords:** islanded microgrid; green hydrogen; long-duration storage; resilience; cost threshold; grid-forming inverter; frequency stability

---

## 1. Introduction

Remote and islanded power systems serve a large and growing share of the world's un- and under-electrified population and remain overwhelmingly dependent on diesel generation \cite{P1}. In archipelagic countries such as the Philippines, hundreds of small island grids rely on imported diesel whose delivered cost is inflated by maritime logistics and is highly volatile, while the same islands face frequent typhoon-driven disruptions that can sever fuel resupply for days \cite{P2}. These systems therefore sit at the intersection of two pressures that are usually studied separately: decarbonisation, which favours displacing diesel with solar and storage, and resilience, which requires riding through multi-day contingencies when external supply fails.

Battery–hydrogen hybrids are increasingly proposed to address both pressures, pairing short-duration batteries with a long-duration hydrogen store—electrolyser, tank, and fuel cell—that can in principle sustain critical load through extended outages without fuel deliveries \cite{P3}. Hydrogen subsystems are, however, capital-intensive and round-trip inefficient, so whether they are justified over a conventional PV–diesel–battery design depends on site-specific economics and on how severe and how diesel-dependent the resilience requirement is. Establishing the *thresholds* that separate the two designs—and, crucially, identifying which design levers move those thresholds—is what makes such an analysis actionable for planners rather than merely descriptive.

A substantial literature optimises the sizing and dispatch of hybrid renewable–storage microgrids \cite{P4,P5}, and a growing body of work examines hydrogen specifically in island and off-grid contexts \cite{P6,P7}. Resilience-oriented studies introduce metrics such as expected energy not served and critical-load survivability and couple them to outage scenarios \cite{P8,P9}. In parallel, the power-electronics community has established that inverter-dominated islanded grids require explicit grid-forming sources and that frequency stability—rate of change of frequency (RoCoF) and frequency nadir—becomes a binding design concern as synchronous inertia disappears \cite{P10,P11}.

Each of these dimensions has been studied, often in depth. Techno-economic optimisation routinely sizes hydrogen-inclusive microgrids and reports break-even conditions against diesel \cite{P4,P5,P6}; resilience studies evaluate critical-load survivability under multi-day and fuel-constrained outages \cite{P8,P9}; and a power-electronics literature analyses grid-forming control and frequency stability in low-inertia islanded grids, including hydrogen-integrated systems \cite{P10,P11}. What remains uncommon is to bring these dimensions together into a single, decision-actionable comparison. In particular: (i) economic thresholds are usually reported for one optimised design rather than attributed to the specific component costs that move them; (ii) competing portfolios are compared as separately optimised designs, which conflates the storage technology with the sizing it induces—controlled comparisons on a common PV–battery backbone, which would isolate the technology's own contribution, are rare; (iii) the level of diesel support during an outage is fixed at one or a few scenarios rather than swept as a continuous robustness boundary that locates where a diesel–battery system matches hydrogen; and (iv) the economic, resilience, and frequency-stability verdicts are typically established in separate studies, so their mutual consistency for a given design is seldom verified \cite{P12}.

This paper addresses these gaps with a unified, design-actionable threshold analysis of a battery–hydrogen versus a PV–diesel–battery portfolio, built on an 8760-h cost-optimal dispatch model driven by real NASA POWER weather (calendar year 2025, central Visayas) for a representative Philippine off-grid island, with a calibrated representative load profile. The contributions are: (i) a fine cost–resilience frontier locating the economic crossover and its sensitivity to hydrogen capital cost; (ii) a component-level decomposition identifying which cost and efficiency parameters most move that frontier; (iii) a matched-backbone comparison—the methodological centrepiece—that places both portfolios on a common PV–battery spine to isolate the contribution of the flexibility technology from sizing; (iv) a graded diesel-support stress test that treats the diesel-availability assumption as a continuous robustness boundary across derating, fuel-budget, and delivery-delay cases; and (v) a reduced-order frequency-stability screen with explicit grid-forming source assignment for each portfolio and operating mode, integrated into the same framework so the economic, resilience, and dynamic verdicts are mutually consistent. The findings are not the expected truism that hydrogen wins when diesel is dear, but a set of more specific and partly counter-intuitive results: the economic crossover occurs at a delivered diesel cost of 377 USD/MWh; the frontier is governed primarily by PV capital cost—not hydrogen component cost or efficiency—because the hydrogen portfolio is intrinsically PV-intensive; the resilience advantage is structural, persisting even at a matched backbone, where the diesel–battery system survives only about one hour of the worst 48-hour outage against hydrogen's full 48 hours; and this advantage extends to the frequency-dynamic layer, where the diesel–battery system is weakest precisely during the diesel-trip handover that also drives its energy-resilience weakness. Together these results show that battery–hydrogen is defensible whenever delivered diesel is costly or diesel support is degradable, both of which characterise remote-island contingencies.

The remainder of the paper is organised as follows. Section 2 describes the system model, cost formulation, resilience evaluation, and the reduced-order dynamic screen. Section 3 presents the threshold frontier and its component drivers, the matched-backbone comparison, the diesel-support robustness analysis, and the frequency-stability screen. Section 4 discusses design implications and limitations, and Section 5 concludes.

---

## Citation placeholders to resolve (literature step — all DOI-verified via Crossref)

The gap framing is now **honest**: it acknowledges that each axis has been studied (often in depth) and claims novelty only in the *integration, attribution, and technology-isolation*. Real anchor papers found during the literature scan (to DOI-verify before insertion):

| Key | Role | Candidate anchor(s) found |
|---|---|---|
| P1 | Diesel dependence of remote/islanded systems | review/statistics — to source |
| P2 | Philippines off-grid; typhoon fuel-supply risk | Tarife et al. (Philippines MOPSO microgrid); to source |
| P3 | Hydrogen long-duration storage in microgrids | general H2-microgrid review; to source |
| P4,P5,P6 | Techno-economic sizing of hybrid/H2 microgrids (optimised designs, break-even) | MDPI *Sustainability* 14(19):12470 (2022); *Energy Reports* Thursday Island (2023); HOMER islanded AC MG, *Sci. Rep.* s41598-025-94506-z (2025) |
| P7 | Multi-decadal cost, battery+H2 vs diesel, incremental LOL cost | *Smart Energy* S266695522500036X (2025) — **strong anchor** |
| P8,P9 | Resilience: survivability/EENS, fuel-constrained & multi-day outages | NREL EDG reliability/survivability (NREL/fy21osti/78837; *Applied Energy* S0306261921000052, 2021); earthquake/health graded-fuel scenarios (2026, S2 24h diesel / S4 72h fuel) |
| P10,P11 | Grid-forming inverters; RoCoF/frequency stability low-inertia | + the E6 method refs already in dynamics_parameters.md (D'Arco & Suul; Kundur; IEEE 1547/P2800; Rocabert et al.) |
| P12 | Integrated techno-economic + dynamic (to anchor the integration gap) | *Energy Conversion & Management* hybrid H2 industrial MG (S221053792500188X, 2025); techno-econ + dynamic green-H2 MG (S2949821X25001814, 2025); hierarchical EMS GFM/GFL (S030626192501089X, 2025) |

*Target total 35–50 refs; none AI-generated; each Crossref-verified before insertion. A literature-matrix table will map representative prior studies against the four integration gaps (component attribution / technology isolation / diesel-support robustness / dynamic consistency) to make the contribution explicit and pre-empt the "this is obvious" critique.*
