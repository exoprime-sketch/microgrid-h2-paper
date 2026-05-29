"""Plot E1 fine threshold-contour figures: fig03 (pure cost) and fig03b (resilience-adjusted)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Baseline values from configs/scenarios.json
_BASELINE_DIESEL_COST = 220.0  # costs.diesel_fuel_usd_per_mwh
_BASELINE_H2_MULT = 1.0


def _save_figure(fig: plt.Figure, stem: Path) -> None:
    pdf_path = stem.with_suffix(".pdf")
    png_path = stem.with_suffix(".png")
    fig.savefig(pdf_path, bbox_inches="tight")
    print(f"Wrote {pdf_path}")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    print(f"Wrote {png_path}")


def plot_threshold_contour(
    df: pd.DataFrame,
    delta_col: str,
    title: str,
    output_stem: Path,
) -> None:
    """Filled contour + bold zero-crossing line on the diesel-cost x H2-multiplier plane."""
    # Pivot to 2-D grid using unique case rows (diesel_battery rows carry the delta columns)
    case_df = (
        df[df["scenario"] == "diesel_battery"][
            [
                "delivered_diesel_cost_usd_per_mwh",
                "hydrogen_capex_multiplier",
                delta_col,
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    heatmap = case_df.pivot(
        index="hydrogen_capex_multiplier",
        columns="delivered_diesel_cost_usd_per_mwh",
        values=delta_col,
    ).sort_index(ascending=True)

    X, Y = np.meshgrid(
        heatmap.columns.to_numpy(dtype=float),
        heatmap.index.to_numpy(dtype=float),
    )
    Z = heatmap.to_numpy(dtype=float) / 1_000_000.0  # → million USD/yr

    abs_max = float(np.nanmax(np.abs(Z)))
    abs_max = max(abs_max, 1.0e-6)
    levels = np.linspace(-abs_max, abs_max, 41)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    cf = ax.contourf(X, Y, Z, levels=levels, cmap="RdYlGn_r", extend="both")

    # Bold zero-cost-difference frontier
    if np.nanmin(Z) <= 0.0 <= np.nanmax(Z):
        ax.contour(X, Y, Z, levels=[0.0], colors="black", linewidths=2.5, zorder=3)

    # Baseline marker
    ax.plot(
        _BASELINE_DIESEL_COST,
        _BASELINE_H2_MULT,
        marker="*",
        markersize=14,
        color="white",
        markeredgecolor="black",
        markeredgewidth=0.8,
        zorder=4,
        label=f"Baseline ({_BASELINE_DIESEL_COST:.0f} USD/MWh, ×{_BASELINE_H2_MULT:.1f})",
    )

    cbar = fig.colorbar(cf, ax=ax, pad=0.02)
    cbar.set_label("ΔCost: H₂ − Diesel (million USD/yr)", fontsize=10)

    ax.set_xlabel("Delivered diesel cost (USD/MWh)", fontsize=11)
    ax.set_ylabel("H₂ CAPEX multiplier (×baseline)", fontsize=11)
    ax.set_title(title, fontsize=11)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(100))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.10))
    ax.grid(True, alpha=0.20, linewidth=0.5)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.85)

    fig.tight_layout()
    _save_figure(fig, output_stem)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot E1 fine threshold contour figures.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    results_dir = (
        args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    )
    figures_dir = (
        args.figures_dir if args.figures_dir.is_absolute() else ROOT / args.figures_dir
    )
    figures_dir.mkdir(parents=True, exist_ok=True)

    data_path = results_dir / "sensitivity_fine.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found. Run scripts/run_fine_sweep.py first.")
        raise SystemExit(1)

    df = pd.read_csv(data_path)
    carbon_price = float(df["carbon_price_usd_per_t"].iloc[0])
    outage_h = float(df["outage_duration_hours"].iloc[0])
    subtitle = f"outage={outage_h:.0f} h  |  carbon={carbon_price:.0f} USD/tCO₂"

    plot_threshold_contour(
        df=df,
        delta_col="delta_cost_usd",
        title=f"Threshold Frontier — Pure Annual Cost\n{subtitle}",
        output_stem=figures_dir / "fig03_threshold_contours",
    )

    plot_threshold_contour(
        df=df,
        delta_col="delta_cost_resilience_adjusted_usd",
        title=f"Threshold Frontier — Resilience-Adjusted Cost\n{subtitle}",
        output_stem=figures_dir / "fig03b_threshold_contours_resilience_adjusted",
    )

    print("Done.")


if __name__ == "__main__":
    main()
