"""
Reduced-order primary frequency response model for islanded microgrid screening.

Swing equation (MOD 1 — S_sys explicit in denominator):
    dΔf/dt = f0 / (2 * H_eq * S_sys) * [Σᵢ δPᵢ  -  ΔP_dist(t)  -  D_eq * Δf]

First-order droop for each responding source i:
    τᵢ * d(δPᵢ)/dt  =  -δPᵢ  -  Kᵢ * Δf

Primary response only; secondary/AGC restoration to nominal frequency is
assumed via standard supervisory control and is NOT modelled.
See results/dynamics_parameters.md for parameter values and citations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp

# ------------------------------------------------------------------
# System constants
# ------------------------------------------------------------------
F0: float    = 50.0   # nominal frequency [Hz]
S_SYS: float = 1.65   # system MVA base = peak load [MW]
D_FRAC: float = 1.5   # load self-regulation [% ΔP_load / % Δf]

# ------------------------------------------------------------------
# Dynamics parameters (see results/dynamics_parameters.md for citations)
# ------------------------------------------------------------------
H_BAT_S: float   = 1.0   # battery VSM virtual inertia [s]       D'Arco & Suul 2014
H_DG_S: float    = 2.0   # diesel genset real inertia [s]         Kundur 1994
DROOP_BAT_PCT: float = 5.0   # battery VSM droop [%]              IEEE 1547-2018
DROOP_DG_PCT: float  = 4.0   # diesel governor droop [%]          Kundur 1994
DROOP_FC_PCT: float  = 6.0   # fuel-cell droop [%]                Uzunoglu & Alam 2006
TAU_BAT_S: float = 0.2   # battery inverter time constant [s]     Rocabert et al. 2012
TAU_DG_S: float  = 2.0   # diesel governor time constant [s]      CIGRE WG C4.110
TAU_FC_S: float  = 5.0   # fuel-cell ramp time constant [s]       Li & Bhatt 2011
TAU_ELZ_S: float = 0.1   # electrolyzer fast response [s]         IEEE P2800
K_ELZ_MW_PER_HZ: float  = 0.5   # electrolyzer demand-response gain [MW/Hz]
ELZ_ACTIVE_THRESH_MW: float = 0.5  # min dispatch to include electrolyzer DR

# Capacities from scenarios.json — kept here so dynamics.py is self-contained
_CAP: dict[str, dict[str, float]] = {
    "battery_only":     {"pv": 7.0,  "bat": 2.2, "bat_e": 24.0, "diesel": 0.0, "fc": 0.0, "elz": 0.0},
    "diesel_battery":   {"pv": 2.8,  "bat": 1.5, "bat_e":  8.0, "diesel": 2.4, "fc": 0.0, "elz": 0.0},
    "battery_hydrogen": {"pv": 14.0, "bat": 2.0, "bat_e": 12.0, "diesel": 0.0, "fc": 2.2, "elz": 5.0},
}


def _droop_k(capacity_mw: float, droop_pct: float) -> float:
    """Droop gain K [MW/Hz].  K = capacity / (R * f0) where R = droop_pct/100."""
    return capacity_mw / (droop_pct / 100.0 * F0)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------
@dataclass
class DroopSource:
    name: str
    capacity_mw: float
    k_mw_per_hz: float
    tau_s: float
    initial_mw: float = 0.0


@dataclass
class FreqSystem:
    """Parameterised (portfolio, mode, operating-point) system."""
    label: str
    grid_forming: str
    h_eq_s: float            # equivalent inertia on S_SYS base [s]
    d_eq_mw_per_hz: float    # load self-regulation [MW/Hz]
    sources: list[DroopSource]
    # operating-point snapshot (for reporting)
    op_load_mw:    float = 0.0
    op_pv_mw:      float = 0.0
    op_diesel_mw:  float = 0.0
    op_fc_mw:      float = 0.0
    op_bat_net_mw: float = 0.0
    op_elz_mw:     float = 0.0
    op_hour:       int   = 0
    op_timestamp:  str   = ""


# ------------------------------------------------------------------
# System factory
# ------------------------------------------------------------------
def build_system(portfolio: str, mode: str, op: dict) -> FreqSystem:
    """
    Construct a FreqSystem for (portfolio, mode, operating-point).

    portfolio: 'battery_only' | 'diesel_battery' | 'battery_hydrogen'
    mode:      'normal' | 'outage'
               outage = battery inverter takes over grid-forming after diesel trip
    op:        dict with keys: load_mw, pv_used_mw, diesel_mw, fuel_cell_mw,
                               battery_discharge_mw, battery_charge_mw,
                               electrolyzer_mw, hour, timestamp
    """
    cap = _CAP[portfolio]
    p_load = float(op.get("load_mw", 1.0))
    p_pv   = float(op.get("pv_used_mw", 0.0))
    p_dg   = float(op.get("diesel_mw", 0.0))
    p_fc   = float(op.get("fuel_cell_mw", 0.0))
    p_elz  = float(op.get("electrolyzer_mw", 0.0))
    p_bat  = float(op.get("battery_discharge_mw", 0.0)) - float(op.get("battery_charge_mw", 0.0))

    d_eq = D_FRAC * p_load / F0   # load self-regulation [MW/Hz]

    if portfolio == "battery_only":
        gf = "battery_inverter"
        h_eq = H_BAT_S * cap["bat"] / S_SYS
        sources = [
            DroopSource("battery", cap["bat"], _droop_k(cap["bat"], DROOP_BAT_PCT), TAU_BAT_S, p_bat),
        ]

    elif portfolio == "diesel_battery":
        if mode == "normal":
            gf = "diesel_genset"
            h_eq = H_DG_S * cap["diesel"] / S_SYS
            sources = [
                DroopSource("diesel",  cap["diesel"], _droop_k(cap["diesel"], DROOP_DG_PCT), TAU_DG_S,  p_dg),
                DroopSource("battery", cap["bat"],    _droop_k(cap["bat"],    DROOP_BAT_PCT), TAU_BAT_S, p_bat),
            ]
        else:  # outage: battery takes over grid-forming after diesel trip
            gf = "battery_inverter"
            h_eq = H_BAT_S * cap["bat"] / S_SYS
            sources = [
                DroopSource("battery", cap["bat"], _droop_k(cap["bat"], DROOP_BAT_PCT), TAU_BAT_S, p_bat),
            ]

    elif portfolio == "battery_hydrogen":
        gf = "battery_inverter"
        h_eq = H_BAT_S * cap["bat"] / S_SYS
        sources = [
            DroopSource("battery",   cap["bat"], _droop_k(cap["bat"], DROOP_BAT_PCT), TAU_BAT_S, p_bat),
            DroopSource("fuel_cell", cap["fc"],  _droop_k(cap["fc"],  DROOP_FC_PCT),  TAU_FC_S,  p_fc),
        ]
        if p_elz >= ELZ_ACTIVE_THRESH_MW:
            sources.append(
                DroopSource("elz_dr", min(p_elz, cap["elz"]),
                            K_ELZ_MW_PER_HZ, TAU_ELZ_S, p_elz)
            )
    else:
        raise ValueError(f"Unknown portfolio: {portfolio!r}")

    return FreqSystem(
        label=f"{portfolio}/{mode}/{op.get('hour', 0)}",
        grid_forming=gf, h_eq_s=h_eq, d_eq_mw_per_hz=d_eq, sources=sources,
        op_load_mw=p_load, op_pv_mw=p_pv, op_diesel_mw=p_dg,
        op_fc_mw=p_fc, op_bat_net_mw=p_bat, op_elz_mw=p_elz,
        op_hour=int(op.get("hour", 0)), op_timestamp=str(op.get("timestamp", "")),
    )


# ------------------------------------------------------------------
# ODE
# ------------------------------------------------------------------
def _make_ode_rhs(
    system: FreqSystem, dist_fn: Callable[[float], float]
) -> Callable[[float, np.ndarray], np.ndarray]:
    """
    Build ODE RHS closure.

    State: x = [Δf,  δP₁,  δP₂, ...]

    Swing (MOD 1 — S_SYS explicit in denominator, matching analytic RoCoF):
        dΔf/dt = f0 / (2 * h_eq * S_sys) * [Σ δPᵢ - dist(t) - D_eq * Δf]

    Droop:
        d(δPᵢ)/dt = (-δPᵢ - Kᵢ * Δf) / τᵢ
    """
    K   = np.array([s.k_mw_per_hz for s in system.sources])
    TAU = np.array([s.tau_s       for s in system.sources])
    # MOD 1: S_SYS in denominator — consistent with rocof = f0*ΔP/(2*H_eq*S_sys)
    swing_prefactor = F0 / (2.0 * system.h_eq_s * S_SYS)
    D = system.d_eq_mw_per_hz

    def rhs(t: float, x: np.ndarray) -> np.ndarray:
        delta_f = x[0]
        delta_p = x[1:]
        dist = dist_fn(t)
        ddf  = swing_prefactor * (np.sum(delta_p) - dist - D * delta_f)
        ddp  = (-delta_p - K * delta_f) / TAU
        return np.concatenate(([ddf], ddp))

    return rhs


# ------------------------------------------------------------------
# Simulation
# ------------------------------------------------------------------
def simulate(
    system: FreqSystem,
    dist_fn: Callable[[float], float],
    t_end: float = 30.0,
    dt:    float = 0.01,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Integrate; return (t, Δf, δP_matrix[n_src × n_steps])."""
    n   = len(system.sources)
    x0  = np.zeros(n + 1)
    t_eval = np.arange(0.0, t_end + dt * 0.5, dt)
    rhs = _make_ode_rhs(system, dist_fn)
    sol = solve_ivp(
        rhs, (0.0, t_end), x0, t_eval=t_eval,
        method="RK45", rtol=1e-7, atol=1e-9,
    )
    delta_p = sol.y[1:] if n > 0 else np.zeros((0, len(sol.t)))
    return sol.t, sol.y[0], delta_p


# ------------------------------------------------------------------
# Metrics  (MOD 2: settling relative to Δf(∞), not to zero)
# ------------------------------------------------------------------
def compute_metrics(
    system: FreqSystem,
    t: np.ndarray,
    delta_f: np.ndarray,
    delta_p: np.ndarray,
    dist_kind: str,
    dist_mag_0: float,       # magnitude at t = 0+ (for analytic RoCoF of step)
    dist_mag_final: float,   # plateau magnitude (for analytic SS offset)
) -> dict:
    dt = float(t[1] - t[0]) if len(t) > 1 else 0.01

    K_total = sum(s.k_mw_per_hz for s in system.sources)

    # ── Analytic steady-state frequency offset (primary droop only) ──
    # Δf(∞) = -ΔP_plateau / (ΣKᵢ + D_eq)
    delta_f_ss_analytic = -dist_mag_final / max(K_total + system.d_eq_mw_per_hz, 1e-12)

    # Numeric SS: mean of final 2 s of simulation
    n_avg = max(1, int(2.0 / dt))
    delta_f_ss_num = float(np.mean(delta_f[-n_avg:]))

    # ── Frequency nadir ──
    freq_nadir = F0 + float(np.min(delta_f))

    # ── RoCoF: analytic for step disturbances, numerical max for ramp ──
    if dist_kind in ("load_step", "diesel_trip"):
        rocof = F0 * dist_mag_0 / (2.0 * system.h_eq_s * S_SYS)
    else:
        rocof = float(np.max(np.abs(np.diff(delta_f) / np.diff(t))))

    # ── Settling time relative to Δf(∞) (MOD 2) ──
    # First t_s such that |Δf(t) - Δf_ss| < 0.05 Hz for all t > t_s
    band = 0.05  # Hz
    centered = np.abs(delta_f - delta_f_ss_num)
    out_idx = np.where(centered >= band)[0]
    if len(out_idx) == 0:
        settling_s = float(t[0])            # settled from the start
    elif out_idx[-1] + 1 >= len(t):
        settling_s = float(t[-1])           # not settled within window
    else:
        settling_s = float(t[out_idx[-1] + 1])

    # ── Peak source ramp [MW/s] ──
    if delta_p.size > 0 and delta_p.shape[1] > 1:
        peak_ramp = float(np.max(np.abs(np.diff(delta_p, axis=1) / dt)))
    else:
        peak_ramp = 0.0

    # ── 500 ms windowed RoCoF (relay-relevant average, IEEE P2800 §7.5) ──
    # rocof_500ms = |Δf(0.5s) - Δf(0)| / 0.5   Δf(0)=0 by initial condition
    idx_500ms = min(int(round(0.5 / dt)), len(delta_f) - 1)
    rocof_500ms = float(abs((delta_f[idx_500ms] - delta_f[0]) / 0.5))

    return {
        "freq_nadir_hz":               freq_nadir,
        "rocof_hz_per_s":              rocof,
        "rocof_500ms_hz_per_s":        rocof_500ms,
        "steady_state_freq_offset_hz": delta_f_ss_num,
        "ss_offset_analytic_hz":       delta_f_ss_analytic,
        "settling_time_s":             settling_s,
        "peak_source_ramp_mw_per_s":   peak_ramp,
    }


# ------------------------------------------------------------------
# RoCoF consistency assertion (MOD 1 verification)
# ------------------------------------------------------------------
def assert_rocof_consistency(
    system: FreqSystem,
    dist_mag: float,
    tol: float = 0.01,
) -> tuple[float, float, float, bool]:
    """
    Verify that the ODE's initial dΔf/dt matches the analytic RoCoF formula
    f0 * ΔP / (2 * H_eq * S_sys) to within tol (default 1%).

    Evaluates the ODE RHS at t=0, x=0 with a constant step disturbance and
    compares the result to the analytic expression.  This directly tests that
    S_SYS is correctly included in the denominator (MOD 1).

    Returns: (analytic, from_ode_rhs, rel_error, passed)
    """
    analytic = F0 * dist_mag / (2.0 * system.h_eq_s * S_SYS)

    n   = len(system.sources)
    x0  = np.zeros(n + 1)
    rhs = _make_ode_rhs(system, lambda t: dist_mag)
    rhs0 = rhs(0.0, x0)
    from_rhs = float(abs(rhs0[0]))

    rel_err = abs(from_rhs - analytic) / max(analytic, 1e-12)
    passed  = rel_err < tol
    if not passed:
        raise AssertionError(
            f"RoCoF consistency FAILED: analytic={analytic:.5f} Hz/s, "
            f"ODE-RHS={from_rhs:.5f} Hz/s, rel_err={rel_err:.4%}"
        )
    return analytic, from_rhs, rel_err, passed
