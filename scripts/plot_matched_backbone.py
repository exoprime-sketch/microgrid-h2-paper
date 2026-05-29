"""Plot E3 matched-backbone figures: fig05_matched_backbone.pdf + PNG."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

E1_CROSSOVER_REF = 376.9  # USD/MWh — unmatched baseline from E1/E2

# Line style: solid = bat_e 12 MWh, dashed = bat_e 8 MWh
_STYLES: dict[float, dict] = {
    8.0:  {"linestyle": "--", "marker": "^", "markersize": 7},
    12.0: {"linestyle": "-",  "marker": "o", "markersize": 7},
}
_COLORS: dict[str, str] = {
    "diesel_battery":   "#d62728",   # red family
    "battery_hydrogen": "#2a9d8f",   # teal family
}
_ALPHA_BY_BAT: dict[float, float] = {8.0: 0.70, 12.0: 0.95}


def _save_figure(fig: plt.Figure, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.pdf')}")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.png')}")


def _surv_label(h: float) -> str:
    """Format survivable outage hours for annotation."""
    if h >= 48.0:
        return "48h"
    return f"{h:.0f}h"


def plot_matched_backbone(df: pd.DataFrame, output_stem: Path) -> None:
    """Two-panel figure: (left) crossover vs PV size, (right) worst-case CLSR vs PV size."""

    pv_levels = sorted(df["backbone_pv_mw"].unique())
    bat_levels = sorted(df["backbone_battery_mwh"].unique())

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(12.5, 5.0))

    # ----------------------------------------------------------------
    # LEFT PANEL: crossover diesel cost vs PV size
    # ----------------------------------------------------------------
    # One unique row per backbone (use diesel_battery rows — crossover is same for both)
    cross_df = (
        df[df["scenario"] == "diesel_battery"]
        [["backbone_pv_mw", "backbone_battery_mwh", "crossover_diesel_cost_usd_per_mwh"]]
        .drop_duplicates()
        .copy()
    )

    for bat_e in bat_levels:
        sub = cross_df[cross_df["backbone_battery_mwh"] == bat_e].sort_values("backbone_pv_mw")
        style = _STYLES[bat_e]
        ax_left.plot(
            sub["backbone_pv_mw"],
            sub["crossover_diesel_cost_usd_per_mwh"],
            color="#457b9d",
            alpha=_ALPHA_BY_BAT[bat_e],
            label=f"Battery {bat_e:.0f} MWh",
            **style,
        )

    # Unmatched baseline reference
    ax_left.axhline(
        E1_CROSSOVER_REF, color="black", linewidth=1.8, linestyle=":",
        label=f"Unmatched baseline: {E1_CROSSOVER_REF:.0f} USD/MWh",
    )

    ax_left.set_xticks(pv_levels)
    ax_left.set_xlabel("Common PV capacity (MW)", fontsize=11)
    ax_left.set_ylabel("Crossover diesel cost (USD/MWh)", fontsize=11)
    ax_left.set_title(
        "Economic Crossover vs PV Scale\n"
        "(pure annual cost, carbon=150 USD/tCO2, outage=48 h)",
        fontsize=10,
    )
    ax_left.grid(True, alpha=0.25)
    ax_left.legend(fontsize=9, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3, frameon=False)

    # ----------------------------------------------------------------
    # RIGHT PANEL: worst-case CLSR (min across 10 seeds) vs PV size
    # ----------------------------------------------------------------
    handles_right: list = []
    labels_right: list[str] = []

    for scenario_name in ["diesel_battery", "battery_hydrogen"]:
        color = _COLORS[scenario_name]
        label_base = "Diesel+battery" if scenario_name == "diesel_battery" else "H2+battery"

        for bat_e in bat_levels:
            sub = (
                df[
                    (df["scenario"] == scenario_name)
                    & (df["backbone_battery_mwh"] == bat_e)
                ]
                .sort_values("backbone_pv_mw")
                .copy()
            )
            style = _STYLES[bat_e]
            line, = ax_right.plot(
                sub["backbone_pv_mw"],
                sub["clsr_min"],
                color=color,
                alpha=_ALPHA_BY_BAT[bat_e],
                label=f"{label_base} / {bat_e:.0f} MWh",
                **style,
            )
            handles_right.append(line)
            labels_right.append(f"{label_base} / {bat_e:.0f} MWh")

            # Annotate each point with survivable_outage_h_min
            for _, row in sub.iterrows():
                surv_h = row["survivable_outage_h_min"]
                clsr = row["clsr_min"]
                pv = row["backbone_pv_mw"]
                offset_y = 0.015 if scenario_name == "diesel_battery" else -0.022
                ax_right.annotate(
                    _surv_label(surv_h),
                    xy=(pv, clsr),
                    xytext=(0, 8 if offset_y > 0 else -14),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7,
                    color=color,
                    alpha=0.85,
                )

    ax_right.axhline(1.0, color="black", linewidth=1.2, linestyle="--", alpha=0.6,
                     label="CLSR = 1.0 (full resilience)")
    ax_right.set_xticks(pv_levels)
    ax_right.set_ylim(bottom=max(0.0, df["clsr_min"].min() - 0.05), top=1.08)
    ax_right.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.3f"))
    ax_right.set_xlabel("Common PV capacity (MW)", fontsize=11)
    ax_right.set_ylabel("Worst-case CLSR (min across 10 seeds)", fontsize=11)
    ax_right.set_title(
        "Resilience vs PV Scale\n"
        "(48 h outage, 4/yr, seeds 1-10; labels = survivable_h_min)",
        fontsize=10,
    )
    ax_right.grid(True, alpha=0.25)
    # Add CLSR=1 line to legend
    ax_right.legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False)

    fig.suptitle(
        "Matched-Backbone Comparison: Flexibility Technology vs PV+Battery Spine",
        fontsize=12, y=1.01,
    )
    fig.subplots_adjust(bottom=0.20)
    _save_figure(fig, output_stem)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot E3 matched-backbone figures.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    figures_dir = args.figures_dir if args.figures_dir.is_absolute() else ROOT / args.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)

    data_path = results_dir / "matched_backbone.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found. Run scripts/run_matched_backbone.py first.")
        raise SystemExit(1)

    df = pd.read_csv(data_path)
    plot_matched_backbone(df, figures_dir / "fig05_matched_backbone")
    print("Done.")


if __name__ == "__main__":
    main()
