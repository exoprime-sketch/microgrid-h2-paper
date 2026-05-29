"""E1 fine 19x19 threshold-contour sweep: diesel_battery vs battery_hydrogen."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
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
    outage_events_from_config,
    solve_dispatch_model,
)

DIESEL_COSTS: list[float] = [round(100.0 + 50.0 * i, 1) for i in range(19)]  # 100..1000
H2_MULTIPLIERS: list[float] = [round(0.30 + 0.05 * i, 2) for i in range(19)]  # 0.30..1.20
FIXED_OUTAGE_HOURS = 48.0
SWEEP_SCENARIOS = ["diesel_battery", "battery_hydrogen"]

BASELINE_EXPECTED: dict[str, float] = {
    "battery_only":    19_239_599.0,
    "diesel_battery":   2_252_545.0,
    "battery_hydrogen": 3_962_313.0,
}
BASELINE_TOL = 0.001  # 0.1 %


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _scenario_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in config["scenarios"]}


def _config_for_case(
    base: dict[str, Any],
    diesel_cost: float,
    h2_capex_multiplier: float,
    carbon_price: float,
) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg["costs"]["diesel_fuel_usd_per_mwh"] = diesel_cost
    cfg["global"]["carbon_price_usd_per_t"] = carbon_price
    cfg.setdefault("resilience", {})["outage_duration_hours"] = FIXED_OUTAGE_HOURS
    cfg["costs"]["electrolyzer_usd_per_kw"] *= h2_capex_multiplier
    cfg["costs"]["fuel_cell_usd_per_kw"] *= h2_capex_multiplier
    cfg["costs"]["h2_tank_usd_per_kg"] *= h2_capex_multiplier
    return cfg


def _dispatch_cache_key(scenario: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, float]:
    if float(scenario.get("diesel_mw", 0.0)) <= 0.0:
        return (scenario["name"], 0.0)
    effective = (
        float(cfg["costs"]["diesel_fuel_usd_per_mwh"])
        + float(cfg["global"].get("carbon_price_usd_per_t", 0.0))
        * float(cfg["global"]["diesel_co2_t_per_mwh"])
    )
    return (scenario["name"], round(effective, 6))


def _interpolate_crossover(diesel_costs: np.ndarray, deltas: np.ndarray) -> float:
    """Linear interpolation of delivered diesel cost where delta crosses zero."""
    for i in range(len(deltas) - 1):
        d0, d1 = deltas[i], deltas[i + 1]
        if d0 == 0.0:
            return float(diesel_costs[i])
        if d1 == 0.0:
            return float(diesel_costs[i + 1])
        if d0 * d1 < 0.0:
            t = -d0 / (d1 - d0)
            return float(diesel_costs[i] + t * (diesel_costs[i + 1] - diesel_costs[i]))
    return float("nan")


def _run_baseline_guard(
    data: pd.DataFrame,
    base_config: dict[str, Any],
    solver_name: str,
    tee: bool,
) -> None:
    print("=" * 64)
    print("BASELINE REPRODUCTION GUARD")
    print("=" * 64)
    scenarios = _scenario_by_name(base_config)
    outage_events = outage_events_from_config(base_config, len(data))
    errors: list[str] = []
    for name, expected in BASELINE_EXPECTED.items():
        scenario = scenarios[name]
        model = build_dispatch_model(data, scenario, base_config)
        solve_dispatch_model(model, solver_name=solver_name, tee=tee)
        dispatch = extract_dispatch(model, data, scenario)
        summary = calculate_summary(dispatch, scenario, base_config)
        actual = float(summary["total_annual_cost_usd"])
        rel_err = abs(actual - expected) / expected
        status = "PASS" if rel_err <= BASELINE_TOL else "FAIL"
        print(
            f"  {name:<22}  expected={expected:>13,.0f}  "
            f"actual={actual:>13,.0f}  err={rel_err:.4%}  {status}"
        )
        if rel_err > BASELINE_TOL:
            errors.append(
                f"{name}: expected {expected:.0f}, got {actual:.0f} (err={rel_err:.4%})"
            )
    if errors:
        print("\nBaseline guard FAILED — aborting sweep:")
        for msg in errors:
            print(f"  {msg}")
        sys.exit(1)
    print("Baseline guard PASSED.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="E1 fine 19x19 threshold-contour sweep.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "scenarios.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--tee", action="store_true", help="Show solver output.")
    parser.add_argument(
        "--carbon-price",
        type=float,
        default=150.0,
        metavar="USD_PER_T",
        help="Carbon price USD/tCO2 (default: 150).",
    )
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    results_dir = (
        args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    carbon_price = args.carbon_price
    n_diesel = len(DIESEL_COSTS)
    n_h2 = len(H2_MULTIPLIERS)
    total_cases = n_diesel * n_h2

    print(f"Carbon price for sweep : {carbon_price:.1f} USD/tCO2")
    print(f"Outage duration fixed  : {FIXED_OUTAGE_HOURS:.0f} h")
    print(
        f"Diesel cost range      : {DIESEL_COSTS[0]:.0f}-{DIESEL_COSTS[-1]:.0f} "
        f"USD/MWh ({n_diesel} levels, step 50)"
    )
    print(
        f"H2 CAPEX mult range    : {H2_MULTIPLIERS[0]:.2f}-{H2_MULTIPLIERS[-1]:.2f} "
        f"({n_h2} levels, step 0.05)"
    )
    print(f"Total sweep cases      : {total_cases} ({n_diesel}x{n_h2})\n")

    base_config = _load_config(config_path)
    dataset_path = ROOT / base_config["dataset"]
    data = pd.read_csv(dataset_path)

    _run_baseline_guard(
        data, base_config, base_config.get("solver", "appsi_highs"), args.tee
    )

    scenarios_map = _scenario_by_name(base_config)
    selected = [scenarios_map[name] for name in SWEEP_SCENARIOS]
    outage_seed = int(base_config.get("resilience", {}).get("random_seed", 123))

    rows: list[dict[str, Any]] = []
    dispatch_cache: dict[tuple[str, float], pd.DataFrame] = {}
    case_id = 0
    lp_solves = 0

    for diesel_cost in DIESEL_COSTS:
        for h2_multiplier in H2_MULTIPLIERS:
            case_id += 1
            case_cfg = _config_for_case(
                base_config,
                diesel_cost=diesel_cost,
                h2_capex_multiplier=h2_multiplier,
                carbon_price=carbon_price,
            )
            events = generate_outage_events(
                n_hours=len(data),
                frequency_per_year=case_cfg.get("resilience", {}).get(
                    "outage_frequency_per_year", 0
                ),
                duration_hours=FIXED_OUTAGE_HOURS,
                seed=outage_seed,
            )

            for scenario in selected:
                cache_key = _dispatch_cache_key(scenario, case_cfg)
                if cache_key not in dispatch_cache:
                    lp_solves += 1
                    print(
                        f"  [LP SOLVE {lp_solves:>2}]  {scenario['name']:<22}"
                        f"  diesel={diesel_cost:>6.0f}  h2_mult={h2_multiplier:.2f}"
                    )
                    model = build_dispatch_model(data, scenario, case_cfg)
                    solve_dispatch_model(
                        model,
                        solver_name=case_cfg.get("solver", "appsi_highs"),
                        tee=args.tee,
                    )
                    dispatch_cache[cache_key] = extract_dispatch(model, data, scenario)

                dispatch = dispatch_cache[cache_key]
                summary = calculate_summary(dispatch, scenario, case_cfg)
                resilience = evaluate_resilience(dispatch, scenario, case_cfg, events=events)
                res_penalty = (
                    resilience["eens_mwh"]
                    * float(
                        case_cfg.get("resilience", {}).get("value_of_lost_load_usd_per_mwh", 0.0)
                    )
                )
                rows.append(
                    {
                        "sensitivity_case": case_id,
                        "scenario": scenario["name"],
                        "label": scenario.get("label", scenario["name"]),
                        "delivered_diesel_cost_usd_per_mwh": diesel_cost,
                        "hydrogen_capex_multiplier": h2_multiplier,
                        "outage_duration_hours": FIXED_OUTAGE_HOURS,
                        "carbon_price_usd_per_t": carbon_price,
                        "total_annual_cost_usd": summary["total_annual_cost_usd"],
                        "lcoe_usd_per_mwh_served": summary["lcoe_usd_per_mwh_served"],
                        "diesel_mwh": summary["diesel_mwh"],
                        "diesel_co2_t": summary["diesel_co2_t"],
                        "carbon_cost_usd": summary["carbon_cost_usd"],
                        "eens_mwh": resilience["eens_mwh"],
                        "lpsp": resilience["lpsp"],
                        "critical_load_served_ratio": resilience["critical_load_served_ratio"],
                        "survivable_outage_duration_h": resilience[
                            "survivable_outage_duration_h"
                        ],
                        "resilience_penalty_usd": res_penalty,
                        "resilience_adjusted_cost_usd": (
                            summary["total_annual_cost_usd"] + res_penalty
                        ),
                    }
                )

    print(
        f"\nSweep complete. "
        f"LP solves: {lp_solves}  "
        f"(cache hits: {total_cases * len(selected) - lp_solves} "
        f"of {total_cases * len(selected)} rows)\n"
    )

    output = pd.DataFrame(rows)
    case_key_cols = [
        "sensitivity_case",
        "delivered_diesel_cost_usd_per_mwh",
        "hydrogen_capex_multiplier",
        "outage_duration_hours",
        "carbon_price_usd_per_t",
    ]
    required_scenarios = {"battery_hydrogen", "diesel_battery"}

    pivot_pure = output.pivot_table(
        index=case_key_cols,
        columns="scenario",
        values="total_annual_cost_usd",
        aggfunc="mean",
    ).reset_index()
    if required_scenarios.issubset(pivot_pure.columns):
        pivot_pure["delta_cost_usd"] = (
            pivot_pure["battery_hydrogen"] - pivot_pure["diesel_battery"]
        )
        pivot_pure["battery_hydrogen_preferred_pure"] = pivot_pure["delta_cost_usd"] < 0.0
        output = output.merge(
            pivot_pure[case_key_cols + ["delta_cost_usd", "battery_hydrogen_preferred_pure"]],
            on=case_key_cols,
            how="left",
        )

    pivot_res = output.pivot_table(
        index=case_key_cols,
        columns="scenario",
        values="resilience_adjusted_cost_usd",
        aggfunc="mean",
    ).reset_index()
    if required_scenarios.issubset(pivot_res.columns):
        pivot_res["delta_cost_resilience_adjusted_usd"] = (
            pivot_res["battery_hydrogen"] - pivot_res["diesel_battery"]
        )
        pivot_res["battery_hydrogen_preferred_resilience"] = (
            pivot_res["delta_cost_resilience_adjusted_usd"] < 0.0
        )
        output = output.merge(
            pivot_res[
                case_key_cols
                + [
                    "delta_cost_resilience_adjusted_usd",
                    "battery_hydrogen_preferred_resilience",
                ]
            ],
            on=case_key_cols,
            how="left",
        )

    sensitivity_path = results_dir / "sensitivity_fine.csv"
    output.to_csv(sensitivity_path, index=False)
    print(f"Wrote {sensitivity_path}")

    # Crossover table — one unique (diesel_cost, h2_mult) row per case
    case_slice = (
        output[output["scenario"] == "diesel_battery"][
            [
                "delivered_diesel_cost_usd_per_mwh",
                "hydrogen_capex_multiplier",
                "delta_cost_usd",
                "delta_cost_resilience_adjusted_usd",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    crossover_rows: list[dict[str, Any]] = []
    for h2_mult, group in case_slice.groupby("hydrogen_capex_multiplier"):
        g = group.sort_values("delivered_diesel_cost_usd_per_mwh")
        dc = g["delivered_diesel_cost_usd_per_mwh"].to_numpy(dtype=float)
        dp = g["delta_cost_usd"].to_numpy(dtype=float)
        dr = g["delta_cost_resilience_adjusted_usd"].to_numpy(dtype=float)
        crossover_rows.append(
            {
                "hydrogen_capex_multiplier": h2_mult,
                "crossover_diesel_cost_pure_usd_per_mwh": _interpolate_crossover(dc, dp),
                "crossover_diesel_cost_resilience_usd_per_mwh": _interpolate_crossover(dc, dr),
            }
        )

    crossover = pd.DataFrame(crossover_rows)
    crossover_path = results_dir / "crossover_diesel_cost.csv"
    crossover.to_csv(crossover_path, index=False)
    print(f"Wrote {crossover_path}\n")

    print("CROSSOVER DIESEL COST TABLE")
    print("=" * 64)
    print(
        f"  {'H2 mult':>8}  {'Crossover pure (USD/MWh)':>26}"
        f"  {'Crossover res-adj (USD/MWh)':>28}"
    )
    print("-" * 64)
    for _, row in crossover.iterrows():
        p = row["crossover_diesel_cost_pure_usd_per_mwh"]
        r = row["crossover_diesel_cost_resilience_usd_per_mwh"]
        p_str = f"{p:>26.1f}" if not pd.isna(p) else f"{'NaN':>26}"
        r_str = f"{r:>28.1f}" if not pd.isna(r) else f"{'NaN':>28}"
        print(f"  {row['hydrogen_capex_multiplier']:>8.2f}  {p_str}  {r_str}")
    print("=" * 64)


if __name__ == "__main__":
    main()
