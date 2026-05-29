"""E2 cost-driver decomposition: crossover diesel cost elasticity for 7 parameters."""

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
    extract_dispatch,
    solve_dispatch_model,
)

DIESEL_COSTS: list[float] = [round(100.0 + 25.0 * i, 1) for i in range(37)]  # 100..1000 step 25
FIXED_OUTAGE_HOURS = 48.0
E1_CROSSOVER_REF = 376.9   # USD/MWh  — E1 step-50 result, used as sanity anchor
CROSSOVER_SANITY_TOL = 5.0  # USD/MWh

PARAMETERS: list[dict[str, Any]] = [
    {"name": "h2_tank_usd_per_kg",         "section": "costs",    "base": 500.0,  "low": 100.0, "high":  600.0, "lp": False},
    {"name": "electrolyzer_usd_per_kw",     "section": "costs",    "base": 900.0,  "low": 360.0, "high": 1080.0, "lp": False},
    {"name": "fuel_cell_usd_per_kw",        "section": "costs",    "base": 1400.0, "low": 560.0, "high": 1680.0, "lp": False},
    {"name": "pv_usd_per_kw",               "section": "costs",    "base": 1200.0, "low": 720.0, "high": 1440.0, "lp": False},
    {"name": "battery_energy_usd_per_kwh",  "section": "costs",    "base": 250.0,  "low": 150.0, "high":  300.0, "lp": False},
    {"name": "electrolyzer_efficiency_lhv", "section": "defaults", "base":   0.67, "low":  0.55, "high":   0.80, "lp": True},
    {"name": "fuel_cell_efficiency_lhv",    "section": "defaults", "base":   0.50, "low":  0.40, "high":   0.65, "lp": True},
]

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


def _dispatch_cache_key(scenario: dict[str, Any], cfg: dict[str, Any]) -> tuple:
    """Extended key: battery_hydrogen keyed by (elec_eff, fc_eff) to support efficiency sweeps."""
    if scenario["name"] == "battery_hydrogen":
        elec_eff = round(float(cfg["defaults"]["electrolyzer_efficiency_lhv"]), 6)
        fc_eff = round(float(cfg["defaults"]["fuel_cell_efficiency_lhv"]), 6)
        return ("battery_hydrogen", elec_eff, fc_eff)
    elif float(scenario.get("diesel_mw", 0.0)) > 0.0:
        effective = (
            float(cfg["costs"]["diesel_fuel_usd_per_mwh"])
            + float(cfg["global"].get("carbon_price_usd_per_t", 0.0))
            * float(cfg["global"]["diesel_co2_t_per_mwh"])
        )
        return ("diesel_battery", round(effective, 6))
    else:
        return (scenario["name"], 0.0)


def _interpolate_crossover(diesel_costs: np.ndarray, deltas: np.ndarray) -> float:
    """Linear interpolation of delivered diesel cost where pure-cost delta crosses zero."""
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


def _make_param_cfg_template(
    base_config: dict[str, Any],
    carbon_price: float,
    param: dict[str, Any] | None = None,
    value: float | None = None,
) -> dict[str, Any]:
    """Deep-copy base config, apply fixed sweep conditions, and optionally perturb one parameter."""
    cfg = copy.deepcopy(base_config)
    cfg["global"]["carbon_price_usd_per_t"] = carbon_price
    cfg.setdefault("resilience", {})["outage_duration_hours"] = FIXED_OUTAGE_HOURS
    if param is not None and value is not None:
        cfg[param["section"]][param["name"]] = value
    return cfg


def _maybe_solve(
    data: pd.DataFrame,
    scenario: dict[str, Any],
    case_cfg: dict[str, Any],
    dispatch_cache: dict,
    solver_name: str,
    tee: bool,
    lp_counter: list[int],
) -> None:
    ck = _dispatch_cache_key(scenario, case_cfg)
    if ck in dispatch_cache:
        return
    lp_counter[0] += 1
    n = lp_counter[0]
    if float(scenario.get("diesel_mw", 0.0)) > 0.0:
        eff_cost = (
            float(case_cfg["costs"]["diesel_fuel_usd_per_mwh"])
            + float(case_cfg["global"].get("carbon_price_usd_per_t", 0.0))
            * float(case_cfg["global"]["diesel_co2_t_per_mwh"])
        )
        info = f"eff_diesel_cost={eff_cost:>7.1f}"
    else:
        elec_eff = float(case_cfg["defaults"]["electrolyzer_efficiency_lhv"])
        fc_eff = float(case_cfg["defaults"]["fuel_cell_efficiency_lhv"])
        info = f"elec_eff={elec_eff:.2f}  fc_eff={fc_eff:.2f}"
    print(f"  [LP SOLVE {n:>2}]  {scenario['name']:<22}  {info}")
    model = build_dispatch_model(data, scenario, case_cfg)
    solve_dispatch_model(model, solver_name=solver_name, tee=tee)
    dispatch_cache[ck] = extract_dispatch(model, data, scenario)


def _compute_crossover(
    data: pd.DataFrame,
    bh_scenario: dict[str, Any],
    db_scenario: dict[str, Any],
    param_cfg_template: dict[str, Any],
    dispatch_cache: dict,
    solver_name: str,
    tee: bool,
    lp_counter: list[int],
) -> float:
    """Sweep diesel costs for a given param config; interpolate and return crossover."""
    deltas: list[float] = []
    for diesel_cost in DIESEL_COSTS:
        case_cfg = copy.deepcopy(param_cfg_template)
        case_cfg["costs"]["diesel_fuel_usd_per_mwh"] = diesel_cost
        _maybe_solve(data, db_scenario, case_cfg, dispatch_cache, solver_name, tee, lp_counter)
        _maybe_solve(data, bh_scenario, case_cfg, dispatch_cache, solver_name, tee, lp_counter)
        bh_cost = calculate_summary(
            dispatch_cache[_dispatch_cache_key(bh_scenario, case_cfg)], bh_scenario, case_cfg
        )["total_annual_cost_usd"]
        db_cost = calculate_summary(
            dispatch_cache[_dispatch_cache_key(db_scenario, case_cfg)], db_scenario, case_cfg
        )["total_annual_cost_usd"]
        deltas.append(bh_cost - db_cost)
    return _interpolate_crossover(np.array(DIESEL_COSTS), np.array(deltas))


def _run_baseline_guard(
    data: pd.DataFrame, base_config: dict[str, Any], solver_name: str, tee: bool
) -> None:
    print("=" * 66)
    print("BASELINE REPRODUCTION GUARD")
    print("=" * 66)
    scenarios = _scenario_by_name(base_config)
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
            errors.append(f"{name}: expected {expected:.0f}, got {actual:.0f} (err={rel_err:.4%})")
    if errors:
        print("\nBaseline guard FAILED -- aborting:")
        for msg in errors:
            print(f"  {msg}")
        sys.exit(1)
    print("Baseline guard PASSED.\n")


def _fmtv(v: float, section: str) -> str:
    return f"{v:.2f}" if section == "defaults" else f"{v:.0f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="E2 cost-driver crossover elasticity sweep.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "scenarios.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--tee", action="store_true", help="Show solver output.")
    parser.add_argument(
        "--carbon-price", type=float, default=150.0, metavar="USD_PER_T",
        help="Carbon price USD/tCO2 (default: 150).",
    )
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    # Guard: must NOT touch the E1 crossover file
    e1_crossover_path = results_dir / "crossover_diesel_cost.csv"

    carbon_price = args.carbon_price
    print(f"Carbon price            : {carbon_price:.1f} USD/tCO2")
    print(f"Outage duration (fixed) : {FIXED_OUTAGE_HOURS:.0f} h")
    print(f"H2 CAPEX multiplier     : 1.0 (baseline, no perturbation)")
    print(f"Diesel cost sweep       : {DIESEL_COSTS[0]:.0f}-{DIESEL_COSTS[-1]:.0f} "
          f"USD/MWh ({len(DIESEL_COSTS)} levels, step 25)")
    print(f"Parameters              : {len(PARAMETERS)}")
    print(f"E1 crossover reference  : {E1_CROSSOVER_REF} USD/MWh\n")

    base_config = _load_config(config_path)
    dataset_path = ROOT / base_config["dataset"]
    data = pd.read_csv(dataset_path)
    solver_name = base_config.get("solver", "appsi_highs")

    _run_baseline_guard(data, base_config, solver_name, args.tee)

    scenarios_map = _scenario_by_name(base_config)
    bh_scenario = scenarios_map["battery_hydrogen"]
    db_scenario = scenarios_map["diesel_battery"]

    dispatch_cache: dict[tuple, pd.DataFrame] = {}
    lp_counter = [0]

    # ----------------------------------------------------------------
    # Baseline crossover sweep (also populates the dispatch cache)
    # ----------------------------------------------------------------
    print("Baseline crossover sweep (37 diesel costs x 2 scenarios)...")
    baseline_cfg = _make_param_cfg_template(base_config, carbon_price)
    baseline_crossover = _compute_crossover(
        data, bh_scenario, db_scenario, baseline_cfg,
        dispatch_cache, solver_name, args.tee, lp_counter,
    )
    n_baseline_solves = lp_counter[0]
    deviation = abs(baseline_crossover - E1_CROSSOVER_REF)
    status = "OK" if deviation <= CROSSOVER_SANITY_TOL else "WARNING -- exceeds tolerance"
    print(
        f"\nBaseline crossover (step-25): {baseline_crossover:.1f} USD/MWh  "
        f"[E1 ref: {E1_CROSSOVER_REF}  |  dev: {deviation:.1f}  {status}]"
    )
    if deviation > CROSSOVER_SANITY_TOL:
        print(f"ERROR: deviation {deviation:.1f} > tolerance {CROSSOVER_SANITY_TOL}. Aborting.")
        sys.exit(1)
    print(f"Baseline sweep LP solves: {n_baseline_solves}  "
          f"(cache now holds {len(dispatch_cache)} dispatch entries)\n")

    # ----------------------------------------------------------------
    # Per-parameter perturbation sweeps
    # ----------------------------------------------------------------
    print("Per-parameter crossover sweeps:")
    print("-" * 66)

    rows: list[dict[str, Any]] = []
    for p in PARAMETERS:
        low_crossovers: list[float] = []
        high_crossovers: list[float] = []

        for level_name, level_value in [("low", p["low"]), ("high", p["high"])]:
            n_before = lp_counter[0]
            param_cfg = _make_param_cfg_template(base_config, carbon_price, p, level_value)
            xover = _compute_crossover(
                data, bh_scenario, db_scenario, param_cfg,
                dispatch_cache, solver_name, args.tee, lp_counter,
            )
            n_new = lp_counter[0] - n_before
            lp_tag = f"  [{n_new} LP solve{'s' if n_new != 1 else ''}]" if n_new > 0 else ""
            xover_str = f"{xover:>7.1f}" if not pd.isna(xover) else "    NaN"
            val_str = _fmtv(level_value, p["section"])
            print(
                f"  {p['name']:32}  {level_name:4} = {val_str:>8}"
                f"  crossover = {xover_str} USD/MWh{lp_tag}"
            )
            if level_name == "low":
                low_crossovers.append(xover)
            else:
                high_crossovers.append(xover)

        low_xo = low_crossovers[0]
        high_xo = high_crossovers[0]
        span = (
            abs(high_xo - low_xo)
            if not (pd.isna(low_xo) or pd.isna(high_xo))
            else float("nan")
        )
        rows.append(
            {
                "parameter": p["name"],
                "config_section": p["section"],
                "baseline_value": p["base"],
                "low_value": p["low"],
                "high_value": p["high"],
                "requires_lp_resolve": p["lp"],
                "baseline_crossover_usd_per_mwh": baseline_crossover,
                "low_crossover_usd_per_mwh": low_xo,
                "high_crossover_usd_per_mwh": high_xo,
                "low_shift_usd_per_mwh": (
                    low_xo - baseline_crossover if not pd.isna(low_xo) else float("nan")
                ),
                "high_shift_usd_per_mwh": (
                    high_xo - baseline_crossover if not pd.isna(high_xo) else float("nan")
                ),
                "crossover_span_usd_per_mwh": span,
            }
        )

    total_sweep_solves = lp_counter[0]
    print(f"\nSweep complete. Total LP solves: {total_sweep_solves}  "
          f"(cache entries: {len(dispatch_cache)})\n")

    # ----------------------------------------------------------------
    # Save elasticity CSV (sorted by span, descending)
    # ----------------------------------------------------------------
    elasticity = pd.DataFrame(rows).sort_values(
        "crossover_span_usd_per_mwh", ascending=False
    ).reset_index(drop=True)

    out_path = results_dir / "cost_driver_elasticity.csv"
    elasticity.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")

    # Verify E1 file untouched
    if e1_crossover_path.exists():
        print(f"E1 crossover file preserved (not modified): {e1_crossover_path}")
    else:
        print(f"NOTE: {e1_crossover_path} not found (E1 not yet run).")

    # ----------------------------------------------------------------
    # Print sorted elasticity table
    # ----------------------------------------------------------------
    print()
    print("COST-DRIVER ELASTICITY TABLE  (sorted by span, descending)")
    print("=" * 90)
    hdr = (
        f"  {'Parameter':<32}  {'Base':>6}  {'Low':>6}  {'High':>6}"
        f"  {'Base XO':>8}  {'Low XO':>8}  {'High XO':>8}  {'Span':>8}"
    )
    print(hdr)
    print("-" * 90)
    for _, row in elasticity.iterrows():
        base_str = _fmtv(row["baseline_value"], row["config_section"])
        low_str  = _fmtv(row["low_value"],      row["config_section"])
        high_str = _fmtv(row["high_value"],      row["config_section"])
        bxo  = f"{row['baseline_crossover_usd_per_mwh']:>8.1f}"
        lxo  = f"{row['low_crossover_usd_per_mwh']:>8.1f}"  if not pd.isna(row['low_crossover_usd_per_mwh'])  else f"{'NaN':>8}"
        hxo  = f"{row['high_crossover_usd_per_mwh']:>8.1f}" if not pd.isna(row['high_crossover_usd_per_mwh']) else f"{'NaN':>8}"
        span = f"{row['crossover_span_usd_per_mwh']:>8.1f}"  if not pd.isna(row['crossover_span_usd_per_mwh'])  else f"{'NaN':>8}"
        print(
            f"  {row['parameter']:<32}  {base_str:>6}  {low_str:>6}  {high_str:>6}"
            f"  {bxo}  {lxo}  {hxo}  {span}"
        )
    print("=" * 90)


if __name__ == "__main__":
    main()
