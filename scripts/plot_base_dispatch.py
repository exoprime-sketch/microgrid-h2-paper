"""Plot fig02_base_dispatch: representative-week hourly dispatch, x-axis in local time (UTC+8).

Display-only timezone shift: df.index + pd.Timedelta(hours=8).
The LP dispatch data is not modified.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

COLORS = {
    "pv_used_mw":           "#f2c14e",
    "diesel_mw":            "#4d4d4d",
    "battery_discharge_mw": "#2a9d8f",
    "fuel_cell_mw":         "#457b9d",
    "unmet_load_mw":        "#d62828",
    "battery_charge_mw":    "#a8dadc",  # light blue, plotted below zero
    "electrolyzer_mw":      "#a8dadc",  # merged with battery charge for bh
}

# PV capacity per scenario (MW) – used only for CF annotation; not modifying data.
_PV_CAP = {"diesel_battery": 2.8, "battery_hydrogen": 14.0}


def _rep_week(df: pd.DataFrame) -> pd.DataFrame:
    """Return 168 rows (Mon-Sun) of the ISO week whose mean PV CF is closest
    to the annual mean – the same criterion used in the evidence base."""
    df = df.copy()
    df.index = pd.to_datetime(df["timestamp"])
    annual_mean_cf = (df["pv_available_mw"] / _PV_CAP.get("battery_hydrogen", 14.0)).mean()
    weeks = df["pv_available_mw"].resample("W-MON", closed="left", label="left")
    week_means = weeks.mean() / _PV_CAP.get("battery_hydrogen", 14.0)
    best_monday = week_means.index[np.argmin(np.abs(week_means.values - annual_mean_cf))]
    start = best_monday
    end   = start + pd.Timedelta(hours=167)
    return df.loc[start:end]


def _read(results_dir: Path, scenario: str) -> pd.DataFrame:
    path = results_dir / f"dispatch_{scenario}.csv"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.set_index("timestamp").sort_index()
    return df


def _plot_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    scenario: str,
    is_bh: bool,
) -> None:
    """Stack supply components and overlay load curve."""
    t = df.index  # UTC timestamps; shifted +8h for display in caller

    # Positive stack: supply to load
    pos_cols = ["pv_used_mw", "diesel_mw", "battery_discharge_mw",
                "fuel_cell_mw", "unmet_load_mw"]
    pos_labels = ["PV used", "Diesel", "Battery discharge", "Fuel cell", "Unmet"]
    pos_colors = [COLORS[c] for c in pos_cols]
    pos_data = [df[c].fillna(0.0).values for c in pos_cols]

    ax.stackplot(t, pos_data, labels=pos_labels, colors=pos_colors, alpha=0.88)

    # Negative stack: charging/electrolyzer (below zero)
    if is_bh:
        neg = -(df["battery_charge_mw"].fillna(0.0) + df["electrolyzer_mw"].fillna(0.0))
        ax.fill_between(t, neg.values, 0, color=COLORS["battery_charge_mw"],
                        alpha=0.70, label="Battery charge + Electrolyzer", step="pre")
    else:
        neg = -df["battery_charge_mw"].fillna(0.0)
        ax.fill_between(t, neg.values, 0, color=COLORS["battery_charge_mw"],
                        alpha=0.70, label="Battery charge", step="pre")

    ax.plot(t, df["load_mw"].values, color="#111111", lw=1.3, label="Load")

    label = "PV + battery + H₂  (battery_hydrogen)" if is_bh else "PV + diesel + battery  (diesel_battery)"
    ax.set_title(label, fontsize=10)
    ax.set_ylabel("Power (MW)", fontsize=9)
    ax.grid(True, alpha=0.20)
    ax.axhline(0, color="#888888", lw=0.6)
    ax.legend(ncol=3, loc="upper left", fontsize=7.5, framealpha=0.80)


def plot_base_dispatch(
    results_dir: Path,
    figures_dir: Path,
) -> None:
    bh = _read(results_dir, "battery_hydrogen")
    db = _read(results_dir, "diesel_battery")

    # Representative week is chosen from battery_hydrogen (14 MW PV = clearest signal)
    bh_week = _rep_week(bh.reset_index())
    monday = bh_week.index[0]
    db_week = db.loc[monday: monday + pd.Timedelta(hours=167)]

    # Display-only shift to local time (UTC+8); LP data is untouched
    UTC_OFFSET = pd.Timedelta(hours=8)
    bh_local = bh_week.copy(); bh_local.index = bh_local.index + UTC_OFFSET
    db_local = db_week.copy(); db_local.index = db_local.index + UTC_OFFSET

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)

    _plot_panel(ax_top, db_local, "diesel_battery", is_bh=False)
    _plot_panel(ax_bot, bh_local, "battery_hydrogen", is_bh=True)

    ax_bot.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    plt.setp(ax_bot.xaxis.get_majorticklabels(), rotation=0, ha="center")
    ax_bot.set_xlabel("Date (2025, local time, UTC+8)", fontsize=10)

    fig.suptitle(
        "Representative-week hourly dispatch  —  base portfolios",
        fontsize=11, y=1.00,
    )
    fig.tight_layout()

    stem = figures_dir / "fig02_base_dispatch"
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.pdf')}")
    fig.savefig(stem.with_suffix(".png"), dpi=200, bbox_inches="tight")
    print(f"Wrote {stem.with_suffix('.png')}")
    plt.close(fig)


def main() -> None:
    results_dir = ROOT / "results"
    figures_dir = ROOT / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    plot_base_dispatch(results_dir, figures_dir)
    print("Done.")


if __name__ == "__main__":
    main()
