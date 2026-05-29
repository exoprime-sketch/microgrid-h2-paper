"""Verify CLSR robustness across many outage seeds at multiple H2 tank sizes."""

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

    tank_sizes_kg = [5_000, 10_000, 15_000, 25_000, 50_000]
    outage_seeds = list(range(1, 51))           # 50 seeds
    outage_durations = [48, 72, 96]              # base + stress

    rows = []
    for tank_kg in tank_sizes_kg:
        print(f"\n=== Solving LP for H2 tank = {tank_kg:,} kg ===")
        scenario = copy.deepcopy(bh_template)
        scenario["h2_tank_kg"] = float(tank_kg)

        model = build_dispatch_model(data, scenario, base_config)
        solve_dispatch_model(
            model, solver_name=base_config.get("solver", "appsi_highs")
        )
        dispatch = extract_dispatch(model, data, scenario)

        for duration in outage_durations:
            for seed in outage_seeds:
                events = generate_outage_events(
                    n_hours=len(data),
                    frequency_per_year=base_config["resilience"][
                        "outage_frequency_per_year"
                    ],
                    duration_hours=duration,
                    seed=seed,
                )
                resilience = evaluate_resilience(
                    dispatch, scenario, base_config, events=events
                )
                rows.append(
                    {
                        "h2_tank_kg": tank_kg,
                        "outage_duration_h": duration,
                        "outage_seed": seed,
                        "critical_load_served_ratio": resilience[
                            "critical_load_served_ratio"
                        ],
                        "eens_mwh": resilience["eens_mwh"],
                        "survivable_outage_h": resilience[
                            "survivable_outage_duration_h"
                        ],
                    }
                )

    df = pd.DataFrame(rows)
    out_path = ROOT / "results" / "outage_seed_robustness.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}")

    # Summary: worst-case CLSR per (tank, duration)
    summary = (
        df.groupby(["h2_tank_kg", "outage_duration_h"])
        .agg(
            clsr_min=("critical_load_served_ratio", "min"),
            clsr_mean=("critical_load_served_ratio", "mean"),
            eens_max=("eens_mwh", "max"),
            survivable_min=("survivable_outage_h", "min"),
        )
        .reset_index()
    )
    print("\nWorst-case CLSR per (tank, duration) across 50 seeds:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()