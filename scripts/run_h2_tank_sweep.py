"""Sweep H2 tank size to find resilience-feasible minimum design."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model import (
    build_dispatch_model,
    calculate_summary,
    evaluate_resilience,
    extract_dispatch,
    generate_outage_events,
    solve_dispatch_model,
)


def main() -> None:
    config_path = ROOT / "configs" / "scenarios.json"
    with config_path.open("r", encoding="utf-8") as f:
        base_config = json.load(f)

    data = pd.read_csv(ROOT / base_config["dataset"])
    bh_template = next(
        s for s in base_config["scenarios"] if s["name"] == "battery_hydrogen"
    )

    tank_sizes_kg = [5_000, 10_000, 15_000, 20_000, 25_000, 30_000, 40_000, 50_000]

    events = generate_outage_events(
        n_hours=len(data),
        frequency_per_year=base_config["resilience"]["outage_frequency_per_year"],
        duration_hours=base_config["resilience"]["outage_duration_hours"],
        seed=int(base_config["resilience"]["random_seed"]),
    )

    rows = []
    for tank_kg in tank_sizes_kg:
        print(f"Solving H2 tank = {tank_kg:>6,} kg ...")
        scenario = copy.deepcopy(bh_template)
        scenario["h2_tank_kg"] = float(tank_kg)

        model = build_dispatch_model(data, scenario, base_config)
        solve_dispatch_model(
            model, solver_name=base_config.get("solver", "appsi_highs")
        )
        dispatch = extract_dispatch(model, data, scenario)

        summary = calculate_summary(dispatch, scenario, base_config)
        resilience = evaluate_resilience(
            dispatch, scenario, base_config, events=events
        )

        rows.append(
            {
                "h2_tank_kg": tank_kg,
                "total_annual_cost_musd": summary["total_annual_cost_usd"] / 1e6,
                "lcoe_usd_per_mwh": summary["lcoe_usd_per_mwh_served"],
                "annual_unmet_mwh": summary["unmet_mwh"],
                "h2_max_used_kg": dispatch["h2_inventory_kg"].max(),
                "h2_tank_utilization": dispatch["h2_inventory_kg"].max() / tank_kg
                if tank_kg > 0
                else 0.0,
                "critical_load_served_ratio": resilience[
                    "critical_load_served_ratio"
                ],
                "eens_mwh": resilience["eens_mwh"],
                "survivable_outage_h": resilience["survivable_outage_duration_h"],
            }
        )

    df = pd.DataFrame(rows)
    out_path = ROOT / "results" / "h2_tank_sweep.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()