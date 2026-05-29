"""Plot E2 cost-driver tornado: fig04_cost_driver_tornado.pdf + PNG."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

PARAM_LABELS: dict[str, str] = {
    "h2_tank_usd_per_kg":          "H₂ tank (USD/kg)",
    "electrolyzer_usd_per_kw":     "Electrolyzer capex (USD/kW)",
    "fuel_cell_usd_per_kw":        "Fuel cell capex (USD/kW)",
    "pv_usd_per_kw":               "PV capex (USD/kW)",
    "battery_energy_usd_per_kwh":  "Battery energy capex (USD/kWh)",
    "electrolyzer_efficiency_lhv": "Electrolyzer efficiency (LHV)",
    "fuel_cell_efficiency_lhv":    "Fuel cell efficiency (LHV)",
}

GREEN = "#2a9d8f"   # H2 more competitive (lower crossover)
RED   = "#e76f51"   # H2 less competitive (higher crossover)
BAR_HEIGHT = 0.55


def _save_figure(fig: plt.Figure, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.pdf')}")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.png')}")


def _fmtv(v: float, section: str) -> str:
    return f"{v:.2f}" if section == "defaults" else f"{v:.0f}"


def plot_tornado(df: pd.DataFrame, output_stem: Path) -> None:
    """Horizontal tornado chart: crossover diesel cost for each parameter at low/high."""
    baseline = float(df["baseline_crossover_usd_per_mwh"].iloc[0])

    # Data for valid rows only (both crossovers finite)
    valid = df[
        df["low_crossover_usd_per_mwh"].notna()
        & df["high_crossover_usd_per_mwh"].notna()
    ].copy()

    n = len(valid)
    y_pos = list(range(n))

    all_xo = pd.concat([valid["low_crossover_usd_per_mwh"], valid["high_crossover_usd_per_mwh"]])
    x_min_data = float(all_xo.min())
    x_max_data = float(all_xo.max())
    x_range = x_max_data - x_min_data
    padding = max(60.0, x_range * 0.18)
    x_left  = x_min_data - padding
    x_right = x_max_data + padding
    annot_offset = max(8.0, x_range * 0.022)

    fig, ax = plt.subplots(figsize=(11.0, 5.0))

    for i, (_, row) in enumerate(valid.iterrows()):
        low_xo  = float(row["low_crossover_usd_per_mwh"])
        high_xo = float(row["high_crossover_usd_per_mwh"])
        sec     = row["config_section"]

        # Absolute bar extents
        bar_left  = min(low_xo, high_xo)
        bar_right = max(low_xo, high_xo)

        # Split at baseline: green left portion, red right portion
        green_right = min(baseline, bar_right)
        if bar_left < green_right:
            ax.barh(i, green_right - bar_left, left=bar_left,
                    height=BAR_HEIGHT, color=GREEN, alpha=0.88, zorder=2)

        red_left = max(baseline, bar_left)
        if red_left < bar_right:
            ax.barh(i, bar_right - red_left, left=red_left,
                    height=BAR_HEIGHT, color=RED, alpha=0.88, zorder=2)

        # End annotations: label each end with the parameter value that produces it
        # If low_xo <= high_xo: left end = low_value, right end = high_value
        # If low_xo >  high_xo: left end = high_value, right end = low_value (inverted)
        if low_xo <= high_xo:
            left_label  = _fmtv(row["low_value"],  sec)
            right_label = _fmtv(row["high_value"], sec)
        else:
            left_label  = _fmtv(row["high_value"], sec)
            right_label = _fmtv(row["low_value"],  sec)

        ax.text(bar_left  - annot_offset, i, left_label,
                ha="right", va="center", fontsize=8, color="#333333")
        ax.text(bar_right + annot_offset, i, right_label,
                ha="left",  va="center", fontsize=8, color="#333333")

    # Baseline reference line
    ax.axvline(baseline, color="black", linewidth=2.0, linestyle="--", zorder=5,
               label=f"Baseline crossover: {baseline:.1f} USD/MWh")

    # Y-axis labels
    y_labels = [PARAM_LABELS.get(row["parameter"], row["parameter"])
                for _, row in valid.iterrows()]
    ax.set_yticks(y_pos)
    ax.set_yticklabels(y_labels, fontsize=10)
    ax.set_xlim(x_left, x_right)
    ax.set_xlabel("Crossover delivered diesel cost (USD/MWh)", fontsize=11)
    ax.set_title(
        "Cost-Driver Sensitivity: Economic Crossover Frontier\n"
        "H₂ vs diesel-battery  |  pure annual cost  |  "
        "carbon = 150 USD/tCO₂  |  outage = 48 h",
        fontsize=11,
    )
    ax.xaxis.set_major_locator(ticker.MultipleLocator(50))
    ax.grid(True, axis="x", alpha=0.25, linewidth=0.5)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.90)

    # Legend patches for color meaning
    import matplotlib.patches as mpatches
    green_patch = mpatches.Patch(color=GREEN, alpha=0.88, label="H₂ more competitive")
    red_patch   = mpatches.Patch(color=RED,   alpha=0.88, label="H₂ less competitive")
    baseline_line = plt.Line2D([0], [0], color="black", linewidth=2.0, linestyle="--",
                               label=f"Baseline: {baseline:.1f} USD/MWh")
    ax.legend(handles=[green_patch, red_patch, baseline_line],
              loc="lower right", fontsize=9, framealpha=0.90)

    fig.tight_layout()
    _save_figure(fig, output_stem)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot E2 cost-driver tornado figure.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    figures_dir = args.figures_dir if args.figures_dir.is_absolute() else ROOT / args.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)

    data_path = results_dir / "cost_driver_elasticity.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found. Run scripts/run_cost_driver.py first.")
        raise SystemExit(1)

    df = pd.read_csv(data_path)

    # df is already sorted by span descending from run_cost_driver.py;
    # re-sort here defensively so the figure is correct even if the CSV was hand-edited.
    df = df.sort_values("crossover_span_usd_per_mwh", ascending=False).reset_index(drop=True)

    plot_tornado(df, figures_dir / "fig04_cost_driver_tornado")
    print("Done.")


if __name__ == "__main__":
    main()
