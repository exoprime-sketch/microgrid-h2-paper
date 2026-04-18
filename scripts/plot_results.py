"""Create publication-oriented baseline figures from dispatch results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

COLORS = {
    "pv_used_mw": "#f2c14e",
    "diesel_mw": "#4d4d4d",
    "battery_discharge_mw": "#2a9d8f",
    "fuel_cell_mw": "#457b9d",
    "unmet_load_mw": "#d62828",
    "load_mw": "#111111",
}


def read_dispatch(results_dir: Path) -> dict[str, pd.DataFrame]:
    dispatch = {}
    for path in sorted(results_dir.glob("dispatch_*.csv")):
        scenario = path.stem.removeprefix("dispatch_")
        data = pd.read_csv(path, parse_dates=["timestamp"])
        dispatch[scenario] = data
    if not dispatch:
        raise FileNotFoundError(f"No dispatch_*.csv files found in {results_dir}")
    return dispatch


def plot_annual_dispatch(dispatch: dict[str, pd.DataFrame], output: Path) -> None:
    fig, axes = plt.subplots(
        len(dispatch), 1, figsize=(12, 2.8 * len(dispatch)), sharex=True
    )
    if len(dispatch) == 1:
        axes = [axes]

    stack_columns = [
        "pv_used_mw",
        "diesel_mw",
        "battery_discharge_mw",
        "fuel_cell_mw",
        "unmet_load_mw",
    ]
    labels = ["PV used", "Diesel", "Battery discharge", "Fuel cell", "Unmet load"]
    colors = [COLORS[column] for column in stack_columns]

    for ax, (scenario, hourly) in zip(axes, dispatch.items()):
        daily = hourly.set_index("timestamp").resample("D").mean(numeric_only=True)
        ax.stackplot(
            daily.index,
            [daily[column] for column in stack_columns],
            labels=labels,
            colors=colors,
            alpha=0.88,
        )
        ax.plot(daily.index, daily["load_mw"], color=COLORS["load_mw"], lw=1.0, label="Load")
        ax.set_ylabel("Daily mean MW")
        ax.set_title(scenario.replace("_", " "))
        ax.grid(True, alpha=0.25)

    axes[0].legend(ncol=3, loc="upper left", fontsize=8)
    axes[-1].set_xlabel("Date")
    fig.suptitle("Annual Dispatch by Scenario", y=0.995)
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def plot_battery_soc(dispatch: dict[str, pd.DataFrame], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    for scenario, data in dispatch.items():
        ax.plot(data["timestamp"], data["battery_soc_mwh"], lw=0.8, label=scenario.replace("_", " "))
    ax.set_title("Battery State of Charge")
    ax.set_ylabel("MWh")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def plot_hydrogen_inventory(dispatch: dict[str, pd.DataFrame], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    for scenario, data in dispatch.items():
        if data["h2_inventory_kg"].max() > 0.0:
            ax.plot(
                data["timestamp"],
                data["h2_inventory_kg"],
                lw=0.9,
                label=scenario.replace("_", " "),
            )
    ax.set_title("Hydrogen Tank Inventory")
    ax.set_ylabel("kg H2")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def plot_cost_comparison(summary: pd.DataFrame, output: Path) -> None:
    components = [
        ("annualized_capital_usd", "Annualized capital", "#457b9d"),
        ("fixed_om_usd", "Fixed O&M", "#2a9d8f"),
        ("diesel_fuel_usd", "Diesel fuel", "#4d4d4d"),
        ("carbon_cost_usd", "Carbon", "#8d99ae"),
        ("variable_om_usd", "Variable O&M", "#f2c14e"),
        ("unmet_load_penalty_usd", "Unmet load penalty", "#d62828"),
    ]

    fig, ax = plt.subplots(figsize=(9, 5))
    labels = summary["label"] if "label" in summary.columns else summary["scenario"]
    bottom = pd.Series([0.0] * len(summary))
    for column, label, color in components:
        if column not in summary.columns:
            continue
        values = summary[column] / 1_000_000.0
        ax.bar(labels, values, bottom=bottom, label=label, color=color)
        bottom += values

    ax.set_title("Annual Cost Comparison")
    ax.set_ylabel("Million USD/year")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _nearest_available(values: pd.Series, requested: float | None) -> float:
    unique = sorted(float(item) for item in values.dropna().unique())
    if not unique:
        raise ValueError("No values available for sensitivity plot filtering.")
    if requested is None:
        return unique[len(unique) // 2]
    return min(unique, key=lambda item: abs(item - requested))


def plot_threshold_heatmap(
    sensitivity: pd.DataFrame, config: dict, output: Path
) -> None:
    settings = config.get("sensitivity", {}).get("heatmap_filter", {})
    outage_duration = _nearest_available(
        sensitivity["outage_duration_hours"],
        settings.get("outage_duration_hours"),
    )
    carbon_price = _nearest_available(
        sensitivity["carbon_price_usd_per_t"],
        settings.get("carbon_price_usd_per_t"),
    )
    filtered = sensitivity[
        (sensitivity["outage_duration_hours"] == outage_duration)
        & (sensitivity["carbon_price_usd_per_t"] == carbon_price)
    ]

    wide = filtered.pivot_table(
        index=[
            "delivered_diesel_cost_usd_per_mwh",
            "hydrogen_capex_multiplier",
        ],
        columns="scenario",
        values="resilience_adjusted_cost_usd",
        aggfunc="mean",
    )
    required = {"diesel_battery", "battery_hydrogen"}
    if not required.issubset(wide.columns):
        return

    wide = wide.reset_index()
    wide["delta_musd"] = (
        wide["battery_hydrogen"] - wide["diesel_battery"]
    ) / 1_000_000.0
    heatmap = wide.pivot(
        index="hydrogen_capex_multiplier",
        columns="delivered_diesel_cost_usd_per_mwh",
        values="delta_musd",
    ).sort_index(ascending=True)

    max_abs = float(np.nanmax(np.abs(heatmap.to_numpy())))
    max_abs = max(max_abs, 1.0e-9)
    fig, ax = plt.subplots(figsize=(8, 5.2))
    image = ax.imshow(
        heatmap.to_numpy(),
        origin="lower",
        aspect="auto",
        cmap="RdYlGn_r",
        vmin=-max_abs,
        vmax=max_abs,
    )
    ax.set_xticks(range(len(heatmap.columns)))
    ax.set_xticklabels([f"{value:.0f}" for value in heatmap.columns])
    ax.set_yticks(range(len(heatmap.index)))
    ax.set_yticklabels([f"{value:.2f}" for value in heatmap.index])
    ax.set_xlabel("Delivered diesel cost (USD/MWh)")
    ax.set_ylabel("Hydrogen CAPEX multiplier")
    ax.set_title(
        "Battery-Hydrogen Threshold\n"
        f"Delta cost vs diesel-battery at {outage_duration:.0f} h outages, "
        f"{carbon_price:.0f} USD/tCO2"
    )
    for row_index, h2_multiplier in enumerate(heatmap.index):
        for column_index, diesel_cost in enumerate(heatmap.columns):
            value = heatmap.loc[h2_multiplier, diesel_cost]
            ax.text(
                column_index,
                row_index,
                f"{value:.1f}",
                ha="center",
                va="center",
                fontsize=8,
                color="#111111",
            )
    if np.nanmin(heatmap.to_numpy()) <= 0.0 <= np.nanmax(heatmap.to_numpy()):
        ax.contour(
            heatmap.to_numpy(),
            levels=[0.0],
            colors="#111111",
            linewidths=1.5,
            origin="lower",
        )
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("Battery-hydrogen minus diesel-battery (million USD/year)")
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def plot_cost_resilience_tradeoff(sensitivity: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    colors = {
        "diesel_battery": "#4d4d4d",
        "battery_hydrogen": "#457b9d",
        "battery_only": "#2a9d8f",
    }
    for scenario, group in sensitivity.groupby("scenario"):
        ax.scatter(
            group["total_annual_cost_usd"] / 1_000_000.0,
            group["critical_load_served_ratio"],
            s=28 + 0.35 * group["outage_duration_hours"],
            alpha=0.65,
            color=colors.get(scenario, "#666666"),
            edgecolor="none",
            label=scenario.replace("_", " "),
        )
    ax.set_xlabel("Annual cost (million USD/year)")
    ax.set_ylabel("Critical load served ratio during outages")
    ax.set_title("Cost-Resilience Tradeoff")
    ax.set_ylim(0.0, 1.03)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "scenarios.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    figures_dir = args.figures_dir if args.figures_dir.is_absolute() else ROOT / args.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(config_path)
    dispatch = read_dispatch(results_dir)
    summary = pd.read_csv(results_dir / "summary.csv")

    plot_annual_dispatch(dispatch, figures_dir / "annual_dispatch.png")
    plot_battery_soc(dispatch, figures_dir / "battery_soc.png")
    plot_hydrogen_inventory(dispatch, figures_dir / "hydrogen_inventory.png")
    plot_cost_comparison(summary, figures_dir / "annual_cost_comparison.png")
    sensitivity_path = results_dir / "sensitivity_summary.csv"
    if sensitivity_path.exists():
        sensitivity = pd.read_csv(sensitivity_path)
        plot_threshold_heatmap(sensitivity, config, figures_dir / "threshold_heatmap.png")
        plot_cost_resilience_tradeoff(
            sensitivity, figures_dir / "cost_resilience_tradeoff.png"
        )
    print(f"Wrote figures to {figures_dir}")


if __name__ == "__main__":
    main()
