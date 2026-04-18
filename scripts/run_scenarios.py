"""Run all configured island microgrid dispatch scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import (
    add_event_timestamps,
    build_dispatch_model,
    calculate_summary,
    evaluate_resilience,
    extract_dispatch,
    outage_events_from_config,
    solve_dispatch_model,
)


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


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

    config = load_config(config_path)
    dataset_path = ROOT / config["dataset"]
    data = pd.read_csv(dataset_path)
    outage_events = outage_events_from_config(config, len(data))
    event_log = add_event_timestamps(outage_events, data["timestamp"])
    if not event_log.empty:
        event_path = results_dir / "outage_events.csv"
        event_log.to_csv(event_path, index=False)
        print(f"Wrote {event_path}")

    summaries = []
    resilience_summaries = []
    for scenario in config["scenarios"]:
        print(f"Solving {scenario['name']}...")
        model = build_dispatch_model(data, scenario, config)
        solve_dispatch_model(model, solver_name=config.get("solver", "appsi_highs"), tee=args.tee)
        dispatch = extract_dispatch(model, data, scenario)
        dispatch_path = results_dir / f"dispatch_{scenario['name']}.csv"
        dispatch.to_csv(dispatch_path, index=False)
        summary = calculate_summary(dispatch, scenario, config)
        resilience = evaluate_resilience(dispatch, scenario, config, events=outage_events)
        resilience_summaries.append(resilience)
        summary.update({key: value for key, value in resilience.items() if key != "scenario"})
        summaries.append(summary)
        print(f"  wrote {dispatch_path}")

    summary = pd.DataFrame(summaries)
    summary_path = results_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)

    resilience_path = results_dir / "resilience_summary.csv"
    pd.DataFrame(resilience_summaries).to_csv(resilience_path, index=False)

    cost_columns = [
        "scenario",
        "label",
        "annualized_capital_usd",
        "fixed_om_usd",
        "diesel_fuel_usd",
        "carbon_cost_usd",
        "variable_om_usd",
        "unmet_load_penalty_usd",
        "total_annual_cost_usd",
        "lcoe_usd_per_mwh_served",
    ]
    annual_costs_path = results_dir / "annual_costs.csv"
    summary[cost_columns].to_csv(annual_costs_path, index=False)
    print(f"Wrote {summary_path}")
    print(f"Wrote {resilience_path}")
    print(f"Wrote {annual_costs_path}")


if __name__ == "__main__":
    main()
