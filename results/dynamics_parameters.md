# E6 Frequency Stability Screening: Model Parameters

## Screening framing

This is a **primary-frequency-response screening model**.  Sustained power
rebalancing after a large PV loss or a generator trip is provided by
secondary control, under-frequency load shedding (UFLS), and hourly
economic dispatch — none of which are in this reduced-order primary model.

**The screen assesses:**
- **RoCoF** (instantaneous and 500 ms windowed) — fast-dynamics relay
  sensitivity
- **Frequency nadir** — lowest frequency during the transient; meaningful
  only when the primary droop reserve is sufficient to arrest the decline
  (*primary_adequate* regime)
- **Primary droop offset** Δf(∞) — the permanent deviation that results from
  primary droop alone, before AGC acts.  For large disturbances this is
  reported as the *secondary-control requirement*, not a stability pass/fail

## Regime classification

| Regime | Condition | Pass/fail logic |
|---|---|---|
| **primary_adequate** | \|Δf(∞)\| < 0.5 Hz | Assess nadir ≥ 49 Hz, RoCoF, settling |
| **secondary_control_dependent** | \|Δf(∞)\| ≥ 0.5 Hz | Report RoCoF only; nadir/settling not assessed — secondary control, UFLS, or dispatch rebalance the power deficit |

## Dual-RoCoF reporting

| Limit | Value | Standard |
|---|---|---|
| Islanded microgrid screen | < 2.0 Hz/s | IEEE P2800; appropriate for no-reconnection-sensitivity systems |
| Mainland interconnected (flag) | < 1.0 Hz/s | EN 50160; UK Grid Code (informational for this study) |

The 500 ms windowed RoCoF  rocof_500ms = (Δf(0.5s) − Δf(0)) / 0.5
contextualises large instantaneous values: e.g., diesel_battery diesel-trip
instantaneous ≈ 27 Hz/s but 500 ms windowed ≈ 4–5 Hz/s, reflecting that
the battery fast droop response (τ = 0.2 s) has already substantially
arrested the decline within the first half-second.

## Critical-load ride-through (diesel_trip rows)

For diesel_battery diesel-trip scenarios, battery_power_mw ≥
0.55 × initial_load_mw is checked.  Even if the battery cannot cover
full load after a diesel trip, it CAN sustain the critical load fraction
(0.55 per config), providing continuity for essential services while
secondary control and UFLS restore full balance.

## VSM inertia design recommendation

battery_hydrogen's 10 % load-step RoCoF at the evening-peak operating
point is 2.06 Hz/s, marginally above the 2.0 Hz/s islanded threshold.
This is addressable by tuning the grid-forming VSM inertia constant H to
≥ 1.2 s (the model uses H = 1.0 s), which is a standard control-parameter
choice well within the range reported in D'Arco & Suul 2014 (H = 0.5–3 s).
This is recommended as a design parameter optimisation, not a structural
constraint.  At H = 1.5 s the RoCoF would reduce to ≈ 1.37 Hz/s,
providing comfortable margin below both thresholds.

## Swing equation and parameters

    dΔf/dt = f0 / (2 * H_eq * S_sys) * [Σᵢ δPᵢ  -  ΔP_dist(t)  -  D_eq * Δf]
    τᵢ d(δPᵢ)/dt  =  -δPᵢ  -  Kᵢ * Δf

S_sys = 1.65 MW (system base = peak load); H_eq = H_gf × S_gf / S_sys.

## Grid-forming assignment

| Portfolio | Mode | Grid-forming source |
|---|---|---|
| battery_only | Normal | Battery inverter (VSM) |
| diesel_battery | Normal | Diesel synchronous generator |
| diesel_battery | Outage | Battery inverter (VSM) after trip |
| battery_hydrogen | Normal | Battery inverter (VSM) |

## Parameter values

| Parameter | Value | Source |
|---|---|---|
| H_bat (virtual inertia) | 1.0 s | D'Arco & Suul, ENERGYCON 2014 |
| H_dg (diesel inertia)   | 2.0 s | Kundur 1994 |
| Droop_bat | 5 % | IEEE 1547-2018 §6.5 |
| Droop_dg  | 4 % | Kundur 1994 §11.2 |
| Droop_fc  | 6 % | Uzunoglu & Alam, IEEE TEC 2006 |
| τ_bat | 0.2 s | Rocabert et al., IEEE TPE 2012 |
| τ_dg  | 2.0 s | CIGRE WG C4.110 |
| τ_fc  | 5.0 s | Li & Bhatt, EPSR 2011 |
| τ_elz | 0.1 s | IEEE P2800 fast frequency response |
| K_elz | 0.5 MW/Hz | 10 % of rated capacity |
| D_eq  | 1.5 × P_load / f0 | Kundur 1994 §7.2 |
| S_sys | 1.65 MW | Peak load (scenarios.json) |

## Screening thresholds

| Metric | Threshold | Basis |
|---|---|---|
| Frequency nadir | ≥ 49.0 Hz | IEC 61727; Philippine ERC Grid Code §5.3.2 |
| RoCoF (islanded) | < 2.0 Hz/s | IEEE P2800 (islanded) |
| RoCoF (mainland flag) | < 1.0 Hz/s | EN 50160; UK Grid Code |
| Settling time | ≤ 30 s | IEEE 1547-2018 §7.5 |
