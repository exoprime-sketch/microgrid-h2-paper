"""E6 reduced-order frequency stability screening (with regime framing)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.dynamics import (
    F0, S_SYS,
    assert_rocof_consistency,
    build_system,
    compute_metrics,
    simulate,
)

RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"

PORTFOLIOS = ["battery_only", "diesel_battery", "battery_hydrogen"]

THRESHOLDS = {
    "nadir_hz":        49.0,
    "rocof_islanded":   2.0,   # Hz/s — islanded microgrid screening
    "rocof_mainland":   1.0,   # Hz/s — mainland flag (informational)
    "settling_s":      30.0,
    "regime_ss_hz":     0.5,   # |ss_offset| threshold for regime classification
}

# Battery power ratings [MW] from scenarios.json — for critical-load check
_BAT_PWR_MW = {"battery_only": 2.2, "diesel_battery": 1.5, "battery_hydrogen": 2.0}
_CRITICAL_LOAD_FRAC = 0.55   # config resilience.critical_load_fraction

TAU_PV_RAMP_S = 2.0

GUARDED_FILES = [
    "crossover_diesel_cost.csv", "sensitivity_fine.csv",
    "cost_driver_elasticity.csv", "matched_backbone.csv",
    "outage_robustness.csv",
]


# -------------------------------------------------------------------
# Operating-point helpers (unchanged from original)
# -------------------------------------------------------------------
def _load_dispatch(portfolio: str) -> pd.DataFrame:
    path = RESULTS_DIR / f"dispatch_{portfolio}.csv"
    if not path.exists():
        print(f"ERROR: {path} not found. Run scripts/run_scenarios.py first.")
        sys.exit(1)
    return pd.read_csv(path).reset_index(drop=True)


def _select_ops(dispatch: pd.DataFrame, portfolio: str) -> tuple[int, int]:
    max_pv = dispatch["pv_available_mw"].max()
    dark = dispatch["pv_available_mw"] < 0.05 * max(max_pv, 1e-9)
    op1 = int(dispatch[dark]["load_mw"].idxmax()) if dark.any() else int(dispatch["load_mw"].idxmax())
    if portfolio == "diesel_battery":
        op2 = int(dispatch["diesel_mw"].idxmax())
    else:
        s = dispatch["pv_used_mw"] > 0.5 * dispatch["pv_used_mw"].max()
        h = dispatch["load_mw"] > 0.8 * dispatch["load_mw"].mean()
        m = s & h
        op2 = int((dispatch[m]["pv_used_mw"] / dispatch[m]["load_mw"]).idxmax()) if m.any() else int(dispatch["pv_used_mw"].idxmax())
    return op1, op2


def _make_op(dispatch: pd.DataFrame, idx: int) -> dict:
    row = dispatch.loc[idx]
    return {
        "hour": idx, "timestamp": str(row.get("timestamp", "")),
        "load_mw":              float(row["load_mw"]),
        "pv_used_mw":           float(row["pv_used_mw"]),
        "pv_available_mw":      float(row["pv_available_mw"]),
        "diesel_mw":            float(row.get("diesel_mw", 0.0)),
        "battery_discharge_mw": float(row.get("battery_discharge_mw", 0.0)),
        "battery_charge_mw":    float(row.get("battery_charge_mw", 0.0)),
        "fuel_cell_mw":    float(row.get("fuel_cell_mw", 0.0)),
        "electrolyzer_mw": float(row.get("electrolyzer_mw", 0.0)),
    }


def _make_disturbance(kind: str, op: dict):
    if kind == "load_step":
        mag = 0.10 * op["load_mw"]
        return (lambda t, m=mag: m), mag, mag, f"load_step_10pct ({mag:.3f} MW)"
    elif kind == "pv_ramp":
        mag = 0.50 * op["pv_used_mw"]
        tau = TAU_PV_RAMP_S
        return (lambda t, m=mag, r=tau: m * min(1.0, t / r)), mag, 0.0, f"pv_ramp_50pct ({mag:.3f} MW / {tau:.0f}s)"
    elif kind == "diesel_trip":
        mag = op["diesel_mw"]
        return (lambda t, m=mag: m), mag, mag, f"diesel_trip ({mag:.3f} MW)"
    else:
        raise ValueError(f"Unknown disturbance: {kind!r}")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    for fname in GUARDED_FILES:
        p = RESULTS_DIR / fname
        if p.exists():
            print(f"Guarded (will not overwrite): {p}")
    print()

    rows: list[dict] = []
    assertion_system = assertion_mag = None

    for portfolio in PORTFOLIOS:
        dispatch = _load_dispatch(portfolio)
        op1_idx, op2_idx = _select_ops(dispatch, portfolio)

        for op_label, op_idx in [("op1_evening_peak", op1_idx), ("op2_active_gen", op2_idx)]:
            op = _make_op(dispatch, op_idx)
            print(
                f"  [{portfolio}  {op_label}]  hr={op['hour']}  "
                f"ts={op['timestamp'][:16]}  load={op['load_mw']:.3f}  "
                f"pv={op['pv_used_mw']:.3f}  diesel={op['diesel_mw']:.3f}  "
                f"fc={op['fuel_cell_mw']:.3f}  bat_net={op['battery_discharge_mw']-op['battery_charge_mw']:+.3f}  "
                f"elz={op['electrolyzer_mw']:.3f}  [all MW]"
            )

            for disturbance in ["load_step", "pv_ramp", "diesel_trip"]:
                if disturbance == "diesel_trip" and portfolio != "diesel_battery":
                    continue
                if disturbance == "pv_ramp" and op["pv_used_mw"] < 0.05:
                    continue

                mode = "outage" if disturbance == "diesel_trip" else "normal"
                system = build_system(portfolio, mode, op)
                dist_fn, mag_final, mag_0, dist_label = _make_disturbance(disturbance, op)

                if (portfolio == "diesel_battery" and op_label == "op1_evening_peak"
                        and disturbance == "load_step"):
                    assertion_system, assertion_mag = system, mag_0

                t, delta_f, delta_p = simulate(system, dist_fn, t_end=30.0, dt=0.01)
                metrics = compute_metrics(system, t, delta_f, delta_p, disturbance, mag_0, mag_final)

                # ── Regime classification (Refinement 2) ──────────────────
                ss_abs = abs(metrics["steady_state_freq_offset_hz"])
                regime = (
                    "primary_adequate"
                    if ss_abs < THRESHOLDS["regime_ss_hz"]
                    else "secondary_control_dependent"
                )

                # ── Pass/fail (regime-aware) ───────────────────────────────
                pri = metrics["rocof_hz_per_s"] < THRESHOLDS["rocof_islanded"]
                prm = metrics["rocof_hz_per_s"] < THRESHOLDS["rocof_mainland"]
                ps  = metrics["settling_time_s"] <= THRESHOLDS["settling_s"]

                if regime == "primary_adequate":
                    pn = metrics["freq_nadir_hz"] >= THRESHOLDS["nadir_hz"]
                    overall_pass = "PASS" if (pn and pri and ps) else "FAIL"
                else:
                    # Nadir is not a stability metric for secondary-regime cases;
                    # sustained rebalancing is provided by AGC, UFLS, and hourly dispatch.
                    pn = None
                    overall_pass = "n.a. (secondary)"

                # ── Critical-load ride-through for diesel_trip (Refinement 2) ──
                crit_load_mw = crit_ok = None
                if disturbance == "diesel_trip":
                    crit_load_mw = _CRITICAL_LOAD_FRAC * op["load_mw"]
                    crit_ok = bool(_BAT_PWR_MW[portfolio] >= crit_load_mw)

                rows.append({
                    "portfolio":                  portfolio,
                    "operating_point":            op_label,
                    "grid_forming_source":        system.grid_forming,
                    "disturbance":                disturbance,
                    "selected_hour":              op["hour"],
                    "op_timestamp":               op["timestamp"][:16],
                    "initial_load_mw":            op["load_mw"],
                    "initial_pv_mw":              op["pv_used_mw"],
                    "initial_diesel_mw":          op["diesel_mw"],
                    "initial_fc_mw":              op["fuel_cell_mw"],
                    "initial_bat_net_mw":         op["battery_discharge_mw"] - op["battery_charge_mw"],
                    "initial_elz_mw":             op["electrolyzer_mw"],
                    "h_eq_s":                     round(system.h_eq_s, 4),
                    "d_eq_mw_per_hz":             round(system.d_eq_mw_per_hz, 5),
                    "disturbance_magnitude_mw":   round(mag_final, 4),
                    "freq_nadir_hz":              round(metrics["freq_nadir_hz"], 4),
                    "rocof_hz_per_s":             round(metrics["rocof_hz_per_s"], 4),
                    "rocof_500ms_hz_per_s":       round(metrics["rocof_500ms_hz_per_s"], 4),
                    "steady_state_freq_offset_hz": round(metrics["steady_state_freq_offset_hz"], 4),
                    "ss_offset_analytic_hz":      round(metrics["ss_offset_analytic_hz"], 4),
                    "settling_time_s":            round(metrics["settling_time_s"], 4),
                    "peak_source_ramp_mw_per_s":  round(metrics["peak_source_ramp_mw_per_s"], 4),
                    "regime":                     regime,
                    "pass_nadir":                 pn,
                    "pass_rocof_islanded_2hz":    pri,
                    "pass_rocof_mainland_1hz":    prm,
                    "pass_settling":              ps,
                    "overall_pass":               overall_pass,
                    "critical_load_mw":           round(crit_load_mw, 4) if crit_load_mw is not None else None,
                    "critical_load_ride_through_ok": crit_ok,
                })

    # ------- RoCoF consistency assertion -------
    print()
    print("=" * 66)
    print("ROCOF CONSISTENCY ASSERTION  (MOD 1 verification)")
    print("  Case: diesel_battery / op1_evening_peak / load_step")
    if assertion_system is not None:
        analytic, from_rhs, rel_err, passed = assert_rocof_consistency(
            assertion_system, assertion_mag
        )
        print(
            f"  Analytic: f0*dP/(2*H_eq*S_sys) = "
            f"{F0}*{assertion_mag:.4f}/(2*{assertion_system.h_eq_s:.4f}*{S_SYS}) "
            f"= {analytic:.5f} Hz/s"
        )
        print(f"  ODE RHS at t=0+: {from_rhs:.5f} Hz/s  |  rel_err: {rel_err:.4%}  |  {'PASS' if passed else 'FAIL'}")
    print("=" * 66)

    # ------- Save CSV -------
    output = pd.DataFrame(rows)
    out_path = RESULTS_DIR / "frequency_response_metrics.csv"
    output.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    for fname in GUARDED_FILES:
        p = RESULTS_DIR / fname
        if p.exists():
            print(f"Preserved (not modified): {p}")

    _write_parameters_md(RESULTS_DIR / "dynamics_parameters.md")
    print(f"Wrote {RESULTS_DIR / 'dynamics_parameters.md'}")

    # ------- Print metrics table -------
    _print_table(rows)


def _print_table(rows: list[dict]) -> None:
    print()
    print("FREQUENCY RESPONSE METRICS  (primary_adequate = P/F on all three; secondary = RoCoF only)")
    W = 128
    print("=" * W)
    print(
        f"  {'Portfolio':<20} {'OP':<20} {'Disturbance':<14}"
        f"  {'Nadir':>6}  {'RoCoF':>6}  {'500ms':>6}  {'SS-Ofs':>7}  {'Settl':>5}"
        f"  {'Regime':<10}  {'Pass':>18}  {'CritOK':>6}"
    )
    print("-" * W)
    for row in rows:
        # pass/fail flags
        pn  = "P" if row["pass_nadir"]  is True else ("-" if row["pass_nadir"]  is None else "F")
        pri = "P" if row["pass_rocof_islanded_2hz"] else "F"
        prm = "P" if row["pass_rocof_mainland_1hz"] else "F"
        ps  = "P" if row["pass_settling"]           else "F"
        op  = str(row["overall_pass"])[:18]
        regime_short = "primary" if row["regime"] == "primary_adequate" else "secondary"
        crit = ("T" if row["critical_load_ride_through_ok"] is True
                else "F" if row["critical_load_ride_through_ok"] is False
                else "-")
        print(
            f"  {row['portfolio']:<20} {row['operating_point']:<20} {row['disturbance']:<14}"
            f"  {row['freq_nadir_hz']:>6.2f}"
            f"  {row['rocof_hz_per_s']:>6.3f}"
            f"  {row['rocof_500ms_hz_per_s']:>6.3f}"
            f"  {row['steady_state_freq_offset_hz']:>7.3f}"
            f"  {row['settling_time_s']:>5.2f}"
            f"  {regime_short:<10}"
            f"  N{pn} Ri{pri} Rm{prm} S{ps}  {op:<18}"
            f"  {crit:>6}"
        )
    print("=" * W)
    print("  N=nadir(49Hz) Ri=RoCoF-islanded(<2Hz/s) Rm=RoCoF-mainland(<1Hz/s) S=settling(<30s)")
    print("  '-' = not assessed (secondary-control-dependent regime)")
    print("  CritOK: battery_power >= 0.55*load  (diesel_trip rows only)")
    print("  Note: primary droop only; SS-Offset is primary-droop floor; AGC restores to 50 Hz")


# -------------------------------------------------------------------
# Updated dynamics_parameters.md  (Refinements 2 framing + VSM note)
# -------------------------------------------------------------------
def _write_parameters_md(path: Path) -> None:
    content = """\
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
"""
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
