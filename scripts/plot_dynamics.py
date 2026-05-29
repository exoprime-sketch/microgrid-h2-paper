"""Plot E6 frequency response traces: fig07_frequency_response.pdf + PNG."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.dynamics import F0, S_SYS, build_system, simulate

TAU_PV_RAMP_S = 2.0   # PV ramp duration [s] — matches run_dynamics.py

RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"

# Portfolio colours
_COL = {
    "battery_only":          "#2a9d8f",
    "diesel_battery_normal": "#555555",
    "diesel_battery_outage": "#c0392b",
    "battery_hydrogen":      "#457b9d",
}
_LABELS = {
    "battery_only":          "PV+battery (bat GF)",
    "diesel_battery_normal": "PV+diesel+bat (diesel GF)",
    "diesel_battery_outage": "PV+diesel+bat (bat GF, post-trip)",
    "battery_hydrogen":      "PV+bat+H₂ (bat GF)",
}


def _save_figure(fig: plt.Figure, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.pdf')}")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.png')}")


def _load_dispatch(portfolio: str) -> pd.DataFrame:
    path = RESULTS_DIR / f"dispatch_{portfolio}.csv"
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
        "load_mw": float(row["load_mw"]), "pv_used_mw": float(row["pv_used_mw"]),
        "diesel_mw": float(row.get("diesel_mw", 0.0)),
        "battery_discharge_mw": float(row.get("battery_discharge_mw", 0.0)),
        "battery_charge_mw":    float(row.get("battery_charge_mw", 0.0)),
        "fuel_cell_mw":    float(row.get("fuel_cell_mw", 0.0)),
        "electrolyzer_mw": float(row.get("electrolyzer_mw", 0.0)),
    }


def _run_case(portfolio, mode, op, dist_kind):
    system = build_system(portfolio, mode, op)
    if dist_kind == "load_step":
        mag = 0.10 * op["load_mw"]
        dist_fn = lambda t, m=mag: m
    elif dist_kind == "pv_ramp":
        mag = 0.50 * op["pv_used_mw"]
        dist_fn = lambda t, m=mag: m * min(1.0, t / TAU_PV_RAMP_S)
    else:  # diesel_trip
        mag = op["diesel_mw"]
        dist_fn = lambda t, m=mag: m
    t, df, dp = simulate(system, dist_fn, t_end=30.0, dt=0.01)
    return t, df, system


def _add_reference_lines(ax, ymin=48.5, draw_49=True):
    ax.axhline(F0,   color="black", linewidth=0.8, linestyle=":", alpha=0.5, zorder=1)
    if draw_49:
        ax.axhline(49.0, color="#d62728", linewidth=1.2, linestyle="--", alpha=0.7,
                   label="49.0 Hz threshold", zorder=1)


def plot_frequency_response(metrics_csv: Path, output_stem: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.8))

    # ── Load ops ──────────────────────────────────────────────────────
    ops: dict[str, dict] = {}
    for p in ["battery_only", "diesel_battery", "battery_hydrogen"]:
        d = _load_dispatch(p)
        i1, i2 = _select_ops(d, p)
        ops[p] = {"op1": _make_op(d, i1), "op2": _make_op(d, i2)}

    # ── Panel A: load step at OP1 (all portfolios) ────────────────────
    ax = axes[0]
    for portfolio, col_key, mode in [
        ("battery_only",     "battery_only",          "normal"),
        ("diesel_battery",   "diesel_battery_normal",  "normal"),
        ("battery_hydrogen", "battery_hydrogen",       "normal"),
    ]:
        op = ops[portfolio]["op1"]
        t, df, sys_ = _run_case(portfolio, mode, op, "load_step")
        freq = F0 + df
        lbl = f"{_LABELS[col_key]}  [H_eq={sys_.h_eq_s:.2f}s]"
        ax.plot(t, freq, color=_COL[col_key], linewidth=1.8, label=lbl)

    _add_reference_lines(ax)
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel("Frequency (Hz)", fontsize=10)
    ax.set_title("A  10 % Load Step — Evening peak\n(all portfolios, primary response only)",
                 fontsize=9.5)
    ax.set_xlim(0, 30); ax.grid(True, alpha=0.20)
    ax.legend(fontsize=7.5, loc='upper center', bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))

    # ── Panel B: PV ramp at OP2 (solar portfolios) ──────────────────
    ax = axes[1]
    drew_something = False
    for portfolio, col_key, mode in [
        ("battery_only",     "battery_only",    "normal"),
        ("battery_hydrogen", "battery_hydrogen", "normal"),
    ]:
        op = ops[portfolio]["op2"]
        if op["pv_used_mw"] < 0.05:
            continue
        t, df, sys_ = _run_case(portfolio, mode, op, "pv_ramp")
        freq = F0 + df
        lbl = f"{_LABELS[col_key]}  (PV={op['pv_used_mw']:.2f} MW)"
        ax.plot(t, freq, color=_COL[col_key], linewidth=1.8, label=lbl)
        drew_something = True

    if not drew_something:
        ax.text(15, 49.9, "PV ≈ 0 at solar period\n(no solar ramp)", ha="center", fontsize=10)

    # Also shade the ramp period
    ax.axvspan(0, TAU_PV_RAMP_S, alpha=0.07, color="gold", label=f"PV ramp ({TAU_PV_RAMP_S:.0f}s)")
    _add_reference_lines(ax)
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_title("B  50 % PV Ramp — Solar period\n(battery-dominated portfolios)", fontsize=9.5)
    ax.set_xlim(0, 30); ax.grid(True, alpha=0.20)
    ax.legend(fontsize=7.5, loc='upper center', bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    # Regime annotation
    ax.text(0.98, 0.03,
            "regime: secondary_control_dependent\nAGC / UFLS handles sustained rebalancing",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7, color="#555555",
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.80))

    # ── Panel C: diesel trip at OP2 (diesel_battery outage mode) ─────
    ax = axes[2]
    op_db = ops["diesel_battery"]["op2"]
    t, df, sys_ = _run_case("diesel_battery", "outage", op_db, "diesel_trip")
    freq = F0 + df
    lbl = (f"{_LABELS['diesel_battery_outage']}\n"
           f"  ΔP={op_db['diesel_mw']:.2f} MW, H_eq={sys_.h_eq_s:.2f}s")
    ax.plot(t, freq, color=_COL["diesel_battery_outage"], linewidth=2.0, label=lbl)

    # Battery_hydrogen load step at OP1 for comparison (reference only)
    op_bh = ops["battery_hydrogen"]["op1"]
    t2, df2, _ = _run_case("battery_hydrogen", "normal", op_bh, "load_step")
    ax.plot(t2, F0 + df2, color=_COL["battery_hydrogen"], linewidth=1.4,
            linestyle="--", alpha=0.7,
            label="H₂+battery load step (ref)")

    _add_reference_lines(ax, draw_49=True)
    ymin_val = min(float(np.min(freq)) - 0.5, 48.0)
    ax.set_ylim(bottom=ymin_val, top=50.4)
    ax.axvline(0, color="#c0392b", linewidth=1.0, linestyle=":", alpha=0.5)
    ax.text(0.5, F0 + 0.2, "← diesel trip", color="#c0392b", fontsize=8, va="bottom")
    # Critical-load ride-through annotation
    crit_load = 0.55 * op_db["load_mw"]
    bat_pwr   = 1.5   # diesel_battery battery_power_mw
    crit_ok   = bat_pwr >= crit_load
    ax.text(0.98, 0.03,
            f"regime: secondary_control_dependent\n"
            f"Battery covers critical load: {bat_pwr:.1f} >= {crit_load:.2f} MW  "
            f"({'OK' if crit_ok else 'NOT OK'})\n"
            f"Full balance: UFLS + secondary control",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7, color="#555555",
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.80))
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_title("C  Diesel Trip + Grid-Forming Handover\n"
                 "(diesel_battery: battery takes over GF at t=0)",
                 fontsize=9.5)
    ax.set_xlim(0, 30); ax.grid(True, alpha=0.20)
    ax.legend(fontsize=7.5, loc='upper center', bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))

    # ── Shared footer ─────────────────────────────────────────────────
    fig.suptitle(
        "Primary Frequency Response Screening  —  Islanded Microgrid\n"
        "Primary response only.  Sustained rebalancing after large PV loss or generator trip: "
        "secondary control / UFLS / dispatch (outside this model).\n"
        "Panel A: primary_adequate (RoCoF + nadir assessed).  "
        "Panels B–C: secondary_control_dependent (RoCoF only).",
        fontsize=8.5, y=1.04,
    )
    fig.subplots_adjust(bottom=0.22)
    _save_figure(fig, output_stem)
    plt.close(fig)


def main() -> None:
    metrics_path = RESULTS_DIR / "frequency_response_metrics.csv"
    if not metrics_path.exists():
        print(f"ERROR: {metrics_path} not found. Run scripts/run_dynamics.py first.")
        raise SystemExit(1)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_frequency_response(metrics_path, FIGURES_DIR / "fig07_frequency_response")
    print("Done.")


if __name__ == "__main__":
    main()
