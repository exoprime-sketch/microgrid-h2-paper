"""Plot E4 outage robustness: fig06_outage_robustness.pdf + PNG."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

E1_CROSSOVER_REF = 376.9  # USD/MWh

# Case-type colours for left panel bars
_CASE_COLORS: dict[str, str] = {
    "D0": "#555555",
    "D1": "#e07b39",
    "D2": "#457b9d",
    "D3": "#2a9d8f",
}
_CLSR_COLOR  = "#8e44ad"
_BH_REF_COLOR = "#d62728"


def _save_figure(fig: plt.Figure, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.pdf')}")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.png')}")


def _ordered_d0d3_db(df: pd.DataFrame) -> pd.DataFrame:
    """Return D0-D3 diesel_battery rows in ROBUSTNESS_CASES order."""
    order = [
        "unavailable",
        "derate_25pct", "derate_50pct", "derate_75pct",
        "fuel_3h", "fuel_6h", "fuel_12h", "fuel_24h",
        "delay_6h", "delay_12h", "delay_24h",
    ]
    sub = (
        df[(df["case_type"].isin(["D0", "D1", "D2", "D3"])) & (df["scenario"] == "diesel_battery")]
        .copy()
    )
    sub["_sort"] = sub["case_label"].map({v: i for i, v in enumerate(order)})
    return sub.sort_values("_sort").reset_index(drop=True)


def plot_outage_robustness(
    df: pd.DataFrame,
    d4_sweep: pd.DataFrame,
    output_stem: Path,
) -> None:
    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(13.5, 5.5))

    # ----------------------------------------------------------------
    # LEFT PANEL: D0-D3 resilience ladder
    # ----------------------------------------------------------------
    d0d3 = _ordered_d0d3_db(df)
    x_pos = np.arange(len(d0d3))

    bar_colors = [_CASE_COLORS[ct] for ct in d0d3["case_type"]]
    bars = ax_left.bar(
        x_pos, d0d3["survivable_outage_h_min"],
        color=bar_colors, alpha=0.85, width=0.65, zorder=2,
    )

    # Secondary axis: clsr_min line
    ax_left2 = ax_left.twinx()
    ax_left2.plot(
        x_pos, d0d3["clsr_min"],
        color=_CLSR_COLOR, marker="D", markersize=5.5,
        linewidth=1.6, linestyle="-", zorder=3, label="CLSR_min (right axis)",
    )
    ax_left2.set_ylim(0.0, 1.12)
    ax_left2.set_ylabel("Worst-case CLSR (right axis)", color=_CLSR_COLOR, fontsize=10)
    ax_left2.tick_params(axis="y", colors=_CLSR_COLOR)

    # BH reference lines
    ax_left.axhline(48.0, color=_BH_REF_COLOR, linewidth=1.8, linestyle="--", zorder=1,
                    label="H2 reference: 48 h")
    ax_left2.axhline(1.0, color=_CLSR_COLOR, linewidth=1.0, linestyle=":", alpha=0.6)

    # Group separators (subtle vertical lines between D0/D1, D1/D2, D2/D3)
    for sep_x in [0.5, 3.5, 7.5]:
        ax_left.axvline(sep_x, color="#cccccc", linewidth=0.8, zorder=1)

    # Group labels
    for group_mid, label in [(0, "D0"), (2, "D1"), (5.5, "D2"), (9, "D3")]:
        ax_left.text(group_mid, -6.5, label, ha="center", fontsize=9,
                     fontweight="bold", color=_CASE_COLORS.get(label, "#333333"))

    ax_left.set_xticks(x_pos)
    ax_left.set_xticklabels(
        [row["case_label"].replace("_", "\n") for _, row in d0d3.iterrows()],
        fontsize=7.5, rotation=0,
    )
    ax_left.set_ylim(bottom=-8, top=55)
    ax_left.set_ylabel("Worst-case survivable outage duration (h)", fontsize=10)
    ax_left.set_title(
        "D0-D3 Diesel Availability — Resilience Impact\n"
        "(diesel_battery, 10 seeds, 48 h/4 events/yr; H₂ always 48 h)",
        fontsize=10,
    )
    ax_left.grid(True, axis="y", alpha=0.25)

    # Legend patches for case types
    legend_patches = [
        mpatches.Patch(color=_CASE_COLORS["D0"], label="D0 unavailable"),
        mpatches.Patch(color=_CASE_COLORS["D1"], label="D1 derated"),
        mpatches.Patch(color=_CASE_COLORS["D2"], label="D2 fuel budget"),
        mpatches.Patch(color=_CASE_COLORS["D3"], label="D3 delayed"),
        plt.Line2D([0], [0], color=_BH_REF_COLOR, linewidth=1.8, linestyle="--",
                   label="H2 reference 48 h"),
        plt.Line2D([0], [0], color=_CLSR_COLOR, marker="D", markersize=5,
                   linewidth=1.5, label="DB CLSR_min"),
    ]
    ax_left.legend(handles=legend_patches, fontsize=7.5, loc='upper center',
                   bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False)

    # ----------------------------------------------------------------
    # RIGHT PANEL: D4 economics
    # ----------------------------------------------------------------
    # Full cost curve from D4 sweep CSV
    x_sweep = d4_sweep["delivered_diesel_cost_usd_per_mwh"].values
    db_sweep = d4_sweep["db_total_annual_cost_usd"].values / 1_000_000.0
    bh_sweep = d4_sweep["bh_total_annual_cost_usd"].values / 1_000_000.0

    ax_right.plot(x_sweep, db_sweep, color="#d62728", linewidth=2.0,
                  label="Diesel+battery (D4: diesel avail.)")
    ax_right.axhline(bh_sweep[0], color="#2a9d8f", linewidth=2.0, linestyle="-",
                     label="H2+battery (carbon=150)")

    # Crossover annotation
    ax_right.axvline(E1_CROSSOVER_REF, color="black", linewidth=1.4, linestyle=":",
                     alpha=0.7, label=f"Crossover ~{E1_CROSSOVER_REF:.0f} USD/MWh")
    ax_right.text(E1_CROSSOVER_REF - 8, ax_right.get_ylim()[0] if False else bh_sweep[0] * 0.995,
                  f"XO\n{E1_CROSSOVER_REF:.0f}", ha="right", va="bottom",
                  fontsize=8, color="black", alpha=0.8)

    # D4 shock price markers on DB line
    d4_db_rows = df[(df["case_type"] == "D4") & (df["scenario"] == "diesel_battery")].copy()
    if not d4_db_rows.empty:
        ax_right.scatter(
            d4_db_rows["delivered_diesel_cost_usd_per_mwh"],
            d4_db_rows["total_annual_cost_usd"] / 1_000_000.0,
            color="#d62728", s=60, zorder=5, marker="o",
        )
        for _, r in d4_db_rows.iterrows():
            ax_right.annotate(
                f"CLSR=1.00\n${r['delivered_diesel_cost_usd_per_mwh']:.0f}",
                xy=(r["delivered_diesel_cost_usd_per_mwh"], r["total_annual_cost_usd"] / 1e6),
                xytext=(0, 10), textcoords="offset points",
                ha="center", va="bottom", fontsize=7.5, color="#d62728",
            )

    # 12 % headroom above the highest data point so topmost label clears the title
    ymax = max(db_sweep.max(), bh_sweep[0]) * 1.15
    ax_right.set_ylim(top=ymax)

    ax_right.set_xlabel("Delivered diesel cost (USD/MWh)", fontsize=11)
    ax_right.set_ylabel("Annual cost (million USD/yr)", fontsize=11)
    ax_right.set_title(
        "D4 Diesel Available — Economic Crossover\n"
        "(carbon=150 USD/tCO₂; CLSR=1.0 for both above crossover)",
        fontsize=10,
    )
    ax_right.xaxis.set_major_locator(ticker.MultipleLocator(100))
    ax_right.grid(True, alpha=0.25)
    ax_right.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18),
                    ncol=3, frameon=False, fontsize=9)

    fig.suptitle(
        "Diesel-Outage Robustness: Graded Support vs H₂ Reference",
        fontsize=12, y=1.01,
    )
    fig.subplots_adjust(bottom=0.22)
    _save_figure(fig, output_stem)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot E4 outage robustness figures.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    figures_dir = args.figures_dir if args.figures_dir.is_absolute() else ROOT / args.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)

    main_path = results_dir / "outage_robustness.csv"
    sweep_path = results_dir / "outage_robustness_d4_sweep.csv"
    for p in [main_path, sweep_path]:
        if not p.exists():
            print(f"ERROR: {p} not found. Run scripts/run_outage_robustness.py first.")
            raise SystemExit(1)

    df      = pd.read_csv(main_path)
    d4_sweep = pd.read_csv(sweep_path)

    plot_outage_robustness(df, d4_sweep, figures_dir / "fig06_outage_robustness")
    print("Done.")


if __name__ == "__main__":
    main()
