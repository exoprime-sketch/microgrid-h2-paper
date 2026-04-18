"""Run publication-oriented cost and resilience sensitivity sweeps."""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import (
    build_dispatch_model,
    calculate_summary,
    evaluate_resilience,
    extract_dispatch,
    generate_outage_events,
    solve_dispatch_model,
)


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _sensitivity_values(config: dict[str, Any], key: str, default: list[float]) -> list[float]:
    return [float(item) for item in config.get("sensitivity", {}).get(key, default)]


def _scenario_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {scenario["name"]: scenario for scenario in config["scenarios"]}


def _config_for_case(
    base_config: dict[str, Any],
    diesel_cost: float,
    outage_duration_hours: float,
    h2_capex_multiplier: float,
    carbon_price: float,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["costs"]["diesel_fuel_usd_per_mwh"] = diesel_cost
    config["global"]["carbon_price_usd_per_t"] = carbon_price
    config.setdefault("resilience", {})["outage_duration_hours"] = outage_duration_hours
    config["costs"]["electrolyzer_usd_per_kw"] *= h2_capex_multiplier
    config["costs"]["fuel_cell_usd_per_kw"] *= h2_capex_multiplier
    config["costs"]["h2_tank_usd_per_kg"] *= h2_capex_multiplier
    return config


def _dispatch_cache_key(scenario: dict[str, Any], config: dict[str, Any]) -> tuple[str, float]:
    if float(scenario.get("diesel_mw", 0.0)) <= 0.0:
        return (scenario["name"], 0.0)
    effective_diesel_cost = (
        float(config["costs"]["diesel_fuel_usd_per_mwh"])
        + float(config["global"].get("carbon_price_usd_per_t", 0.0))
        * float(config["global"]["diesel_co2_t_per_mwh"])
    )
    return (scenario["name"], round(effective_diesel_cost, 6))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "scenarios.json",
    )
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--tee", action="store_true", help="Show solver output.")
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    base_config = load_config(config_path)
    dataset_path = ROOT / base_config["dataset"]
    data = pd.read_csv(dataset_path)
    sensitivity = base_config.get("sensitivity", {})

    diesel_costs = _sensitivity_values(
        base_config, "delivered_diesel_cost_usd_per_mwh", [180.0, 260.0, 340.0]
    )
    outage_durations = _sensitivity_values(
        base_config, "outage_duration_hours", [12.0, 48.0, 96.0]
    )
    h2_capex_multipliers = _sensitivity_values(
        base_config, "hydrogen_capex_multiplier", [0.7, 1.0, 1.3]
    )
    carbon_prices = _sensitivity_values(
        base_config, "carbon_price_usd_per_t", [0.0, 75.0, 150.0]
    )

    scenario_names = sensitivity.get(
        "scenarios", ["diesel_battery", "battery_hydrogen"]
    )
    scenarios = _scenario_by_name(base_config)
    selected_scenarios = [scenarios[name] for name in scenario_names]

    rows: list[dict[str, Any]] = []
    dispatch_cache: dict[tuple[str, float], pd.DataFrame] = {}
    case_id = 0
    total_cases = (
        len(diesel_costs)
        * len(outage_durations)
        * len(h2_capex_multipliers)
        * len(carbon_prices)
    )

    for diesel_cost, outage_duration, h2_multiplier, carbon_price in itertools.product(
        diesel_costs, outage_durations, h2_capex_multipliers, carbon_prices
    ):
        case_id += 1
        case_config = _config_for_case(
            base_config,
            diesel_cost=diesel_cost,
            outage_duration_hours=outage_duration,
            h2_capex_multiplier=h2_multiplier,
            carbon_price=carbon_price,
        )
        events = generate_outage_events(
            n_hours=len(data),
            frequency_per_year=case_config.get("resilience", {}).get(
                "outage_frequency_per_year", 0
            ),
            duration_hours=outage_duration,
            seed=int(case_config.get("resilience", {}).get("random_seed", 123)),
        )
        print(
            "Sensitivity case "
            f"{case_id}/{total_cases}: diesel={diesel_cost}, outage_h={outage_duration}, "
            f"h2_capex_x={h2_multiplier}, carbon={carbon_price}"
        )

        for scenario in selected_scenarios:
            cache_key = _dispatch_cache_key(scenario, case_config)
            if cache_key not in dispatch_cache:
                model = build_dispatch_model(data, scenario, case_config)
                solve_dispatch_model(
                    model,
                    solver_name=case_config.get("solver", "appsi_highs"),
                    tee=args.tee,
                )
                dispatch_cache[cache_key] = extract_dispatch(model, data, scenario)

            dispatch = dispatch_cache[cache_key]
            summary = calculate_summary(dispatch, scenario, case_config)
            resilience = evaluate_resilience(dispatch, scenario, case_config, events=events)
            resilience_penalty_usd = (
                resilience["eens_mwh"]
                * float(case_config.get("resilience", {}).get("value_of_lost_load_usd_per_mwh", 0.0))
            )
            rows.append(
                {
                    "sensitivity_case": case_id,
                    "scenario": scenario["name"],
                    "label": scenario.get("label", scenario["name"]),
                    "delivered_diesel_cost_usd_per_mwh": diesel_cost,
                    "outage_duration_hours": outage_duration,
                    "hydrogen_capex_multiplier": h2_multiplier,
                    "carbon_price_usd_per_t": carbon_price,
                    "total_annual_cost_usd": summary["total_annual_cost_usd"],
                    "lcoe_usd_per_mwh_served": summary["lcoe_usd_per_mwh_served"],
                    "diesel_mwh": summary["diesel_mwh"],
                    "diesel_co2_t": summary["diesel_co2_t"],
                    "carbon_cost_usd": summary["carbon_cost_usd"],
                    "eens_mwh": resilience["eens_mwh"],
                    "lpsp": resilience["lpsp"],
                    "critical_load_served_ratio": resilience[
                        "critical_load_served_ratio"
                    ],
                    "survivable_outage_duration_h": resilience[
                        "survivable_outage_duration_h"
                    ],
                    "resilience_penalty_usd": resilience_penalty_usd,
                    "resilience_adjusted_cost_usd": summary["total_annual_cost_usd"]
                    + resilience_penalty_usd,
                }
            )

    output = pd.DataFrame(rows)
    case_columns = [
        "sensitivity_case",
        "delivered_diesel_cost_usd_per_mwh",
        "outage_duration_hours",
        "hydrogen_capex_multiplier",
        "carbon_price_usd_per_t",
    ]
    paired = output.pivot_table(
        index=case_columns,
        columns="scenario",
        values="resilience_adjusted_cost_usd",
        aggfunc="mean",
    )
    if {"battery_hydrogen", "diesel_battery"}.issubset(paired.columns):
        paired = paired.reset_index()
        paired["battery_hydrogen_minus_diesel_battery_usd"] = (
            paired["battery_hydrogen"] - paired["diesel_battery"]
        )
        paired["battery_hydrogen_preferred_to_diesel_battery"] = (
            paired["battery_hydrogen_minus_diesel_battery_usd"] < 0.0
        )
        output = output.merge(
            paired[
                case_columns
                + [
                    "battery_hydrogen_minus_diesel_battery_usd",
                    "battery_hydrogen_preferred_to_diesel_battery",
                ]
            ],
            on=case_columns,
            how="left",
        )
    output_path = results_dir / "sensitivity_summary.csv"
    output.to_csv(output_path, index=False)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
