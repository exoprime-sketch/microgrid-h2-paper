# APEN-D-26-09220 — Submission front matter

## Highlights
*(Applied Energy: 3–5 bullets, ≤ 85 characters each incl. spaces)*

- Battery–hydrogen is cheaper than PV–diesel above 378 USD/MWh delivered diesel
- PV capital cost—not converter efficiency—sets the cost–resilience threshold
- Matched-backbone test shows the resilience edge is intrinsic to H2 storage
- Any diesel start-up delay collapses diesel–battery survivability to zero
- Reduced-order frequency screen confirms islanded dynamic feasibility

---

## Cover letter

Dear Editor,

Please find enclosed the revised manuscript **APEN-D-26-09220**, "Design-actionable cost–resilience thresholds for islanded battery–hydrogen microgrids: component drivers, diesel-support robustness, and dynamic feasibility," submitted for consideration in *Applied Energy* as a major revision of our earlier submission.

We are grateful to the three reviewers, whose comments have materially improved the work. In response we have added five new analyses, all reproducible from the released code: a finely resolved, carbon-priced cost–resilience threshold contour; a cost-driver attribution identifying which design parameters move that threshold; a matched-backbone experiment that isolates the contribution of the flexibility technology from that of the shared PV–battery backbone; a graded diesel-support robustness study relaxing the diesel-unavailability assumption; and a reduced-order frequency-response screen of the islanded contingencies with an explicit grid-forming reference for each portfolio. We have also rewritten the introduction and literature positioning, made the optimisation and cost formulation fully explicit, clarified the role and sizing of PV, and corrected and clarified the description of the input data.

The central contribution is no longer the qualitative observation that hydrogen becomes attractive when diesel is costly, but the design-actionable structure behind it: that PV capital cost rather than converter efficiency sets the threshold; that the resilience advantage is intrinsic to the long-duration hydrogen store rather than a by-product of sizing; that the diesel alternative's resilience is fragile to realistic support degradation, with any start-up delay collapsing worst-case survivability; and that these conclusions are dynamically feasible for an islanded system. A point-by-point response to each reviewer accompanies this letter.

The manuscript is original, has not been published previously, and is not under consideration elsewhere. All code, configuration, and data needed to reproduce every figure and table are openly archived (Zenodo DOI 10.5281/zenodo.19658748). The author declares no competing interests.

Thank you for your consideration.

Sincerely,
Jaewon Lee
National Institute of Green Technology, Republic of Korea

---

## Declarations

**CRediT author statement.** Jaewon Lee: Conceptualization, Methodology, Software, Formal analysis, Investigation, Data curation, Writing – original draft, Writing – review & editing, Visualization. (Single author.)

**Declaration of competing interest.** The author declares that he has no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

**Funding.** [State funding source(s) and grant number(s), or: "This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors."]

**Declaration of generative AI use.** [If required by the journal: state any use of generative-AI tools in manuscript preparation, per Applied Energy policy. Tools used for analysis/code should be described in Methods/Data availability as appropriate.]

**Data availability.** All code, model configuration, input data (real NASA POWER 2025 weather and the calibrated load profile), and the scripts that generate every figure and table are openly available at GitHub (github.com/exoprime-sketch/microgrid-h2-paper) and archived at Zenodo (DOI 10.5281/zenodo.19658748).

---

> To finalise: fill the funding and generative-AI declarations per journal policy;
> recount each highlight against the 85-character limit in the submission system;
> confirm affiliation/address formatting matches the title page.
