"""E3 matched-backbone comparison: diesel_battery vs battery_hydrogen on a common PV+battery spine."""

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
    solve_dispatch_model,
)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
DIESEL_COSTS: list[float] = [round(100.0 + 50.0 * i, 1) for i in range(19)]  # 100..1000 step 50
DIESEL_COST_REF = 220.0          # reference price for cost/resilience reporting
DIESEL_COST_REF_LOWER = 200.0    # nearest step-50 below 220 (in sweep)
DIESEL_COST_REF_UPPER = 250.0    # nearest step-50 above 220 (in sweep)
REF_INTERP_T = (DIESEL_COST_REF - DIESEL_COST_REF_LOWER) / (DIESEL_COST_REF_UPPER - DIESEL_COST_REF_LOWER)  # 0.4

RESILIENCE_SEEDS: list[int] = list(range(1, 11))  # seeds 1-10
FIXED_OUTAGE_HOURS = 48.0
OUTAGE_FREQ_PER_YEAR = 4
BACKBONE_EP_RATIO = 6.0  # h  (battery_hydrogen baseline: 12 MWh / 2.0 MW)

PV_SIZES: list[float] = [7.0, 10.0, 14.0]
BATTERY_ENERGIES: list[float] = [8.0, 12.0]
BACKBONES: list[tuple[float, float]] = [(pv, be) for pv in PV_SIZES for be in BATTERY_ENERGIES]
SWEEP_SCENARIOS = ["diesel_battery", "battery_hydrogen"]

BASELINE_EXPECTED: dict[str, float] = {
    "battery_only":    19_239_599.0,
    "diesel_battery":   2_252_545.0,
    "battery_hydrogen": 3_962_313.0,
}
BASELINE_TOL = 0.001

# Files that must NOT be overwritten
GUARDED_FILES = [
    "crossover_diesel_cost.csv",
    "sensitivity_fine.csv",
    "cost_driver_elasticity.csv",
]


# ------------------------------------------------------------------
# Config / scenario helpers
# ------------------------------------------------------------------
def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _scenario_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in config["scenarios"]}


def _make_matched_scenario(
    base_scenario: dict[str, Any],
    pv_mw: float,
    bat_e_mwh: float,
    bat_p_mw: float,
) -> dict[str, Any]:
    """Deep-copy scenario and override PV/battery backbone capacities."""
    s = copy.deepcopy(base_scenario)
    s["pv_mw"] = pv_mw
    s["battery_energy_mwh"] = bat_e_mwh
    s["battery_power_mw"] = bat_p_mw
    return s


def _make_backbone_cfg(base_config: dict[str, Any], carbon_price: float) -> dict[str, Any]:
    """Deep-copy base config and apply fixed sweep conditions (no diesel cost yet)."""
    cfg = copy.deepcopy(base_config)
    cfg["global"]["carbon_price_usd_per_t"] = carbon_price
    cfg.setdefault("resilience", {})["outage_duration_hours"] = FIXED_OUTAGE_HOURS
    return cfg


# ------------------------------------------------------------------
# Dispatch cache key — includes (pv_mw, bat_e_mwh) since both change LP
# ------------------------------------------------------------------
def _dispatch_cache_key(scenario: dict[str, Any], cfg: dict[str, Any]) -> tuple:
    pv = round(float(scenario.get("pv_mw", 0.0)), 4)
    bat_e = round(float(scenario.get("battery_energy_mwh", 0.0)), 4)
    if scenario["name"] == "battery_hydrogen":
        return ("battery_hydrogen", pv, bat_e)
    elif float(scenario.get("diesel_mw", 0.0)) > 0.0:
        effective = (
            float(cfg["costs"]["diesel_fuel_usd_per_mwh"])
            + float(cfg["global"].get("carbon_price_usd_per_t", 0.0))
            * float(cfg["global"]["diesel_co2_t_per_mwh"])
        )
        return ("diesel_battery", pv, bat_e, round(effective, 6))
    else:
        return (scenario["name"], pv, bat_e)


def _interpolate_crossover(diesel_costs: np.ndarray, deltas: np.ndarray) -> float:
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
    pv = scenario.get("pv_mw", 0.0)
    bat_e = scenario.get("battery_energy_mwh", 0.0)
    if float(scenario.get("diesel_mw", 0.0)) > 0.0:
        eff = (
            float(case_cfg["costs"]["diesel_fuel_usd_per_mwh"])
            + float(case_cfg["global"].get("carbon_price_usd_per_t", 0.0))
            * float(case_cfg["global"]["diesel_co2_t_per_mwh"])
        )
        info = f"pv={pv:.1f}  bat_e={bat_e:.1f}  eff_diesel={eff:.1f}"
    else:
        info = f"pv={pv:.1f}  bat_e={bat_e:.1f}"
    print(f"  [LP SOLVE {lp_counter[0]:>3}]  {scenario['name']:<22}  {info}")
    model = build_dispatch_model(data, scenario, case_cfg)
    solve_dispatch_model(model, solver_name=solver_name, tee=tee)
    dispatch_cache[ck] = extract_dispatch(model, data, scenario)


def _compute_crossover(
    data: pd.DataFrame,
    bh_scenario: dict[str, Any],
    db_scenario: dict[str, Any],
    backbone_cfg_template: dict[str, Any],
    dispatch_cache: dict,
    solver_name: str,
    tee: bool,
    lp_counter: list[int],
) -> float:
    deltas: list[float] = []
    for diesel_cost in DIESEL_COSTS:
        case_cfg = copy.deepcopy(backbone_cfg_template)
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


def _evaluate_resilience_multi_seed(
    dispatch: pd.DataFrame,
    scenario: dict[str, Any],
    config: dict[str, Any],
    n_hours: int,
) -> dict[str, float]:
    """Run evaluate_resilience across all RESILIENCE_SEEDS; return worst/mean stats."""
    clsr_list: list[float] = []
    eens_list: list[float] = []
    surv_list: list[float] = []
    for seed in RESILIENCE_SEEDS:
        events = generate_outage_events(
            n_hours=n_hours,
            frequency_per_year=OUTAGE_FREQ_PER_YEAR,
            duration_hours=FIXED_OUTAGE_HOURS,
            seed=seed,
        )
        res = evaluate_resilience(dispatch, scenario, config, events=events)
        clsr_list.append(float(res["critical_load_served_ratio"]))
        eens_list.append(float(res["eens_mwh"]))
        surv_list.append(float(res["survivable_outage_duration_h"]))
    return {
        "clsr_min":               min(clsr_list),
        "clsr_mean":              float(np.mean(clsr_list)),
        "eens_max":               max(eens_list),
        "survivable_outage_h_min": min(surv_list),
    }


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
            errors.append(f"{name}: expected {expected:.0f}, got {actual:.0f}")
    if errors:
        print("\nBaseline guard FAILED -- aborting:")
        for msg in errors:
            print(f"  {msg}")
        sys.exit(1)
    print("Baseline guard PASSED.\n")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="E3 matched-backbone comparison.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "scenarios.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--tee", action="store_true")
    parser.add_argument("--carbon-price", type=float, default=150.0, metavar="USD_PER_T")
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    carbon_price = args.carbon_price

    # Confirm guarded files will not be touched
    for fname in GUARDED_FILES:
        p = results_dir / fname
        if p.exists():
            print(f"Guarded (will not overwrite): {p}")

    print(f"\nCarbon price            : {carbon_price:.1f} USD/tCO2")
    print(f"Outage fixed            : {FIXED_OUTAGE_HOURS:.0f} h, {OUTAGE_FREQ_PER_YEAR}/yr")
    print(f"Diesel cost sweep       : {DIESEL_COSTS[0]:.0f}-{DIESEL_COSTS[-1]:.0f} "
          f"({len(DIESEL_COSTS)} levels, step 50)")
    print(f"Reference diesel price  : {DIESEL_COST_REF:.0f} USD/MWh "
          f"(interpolated from {DIESEL_COST_REF_LOWER:.0f} and {DIESEL_COST_REF_UPPER:.0f})")
    print(f"Resilience seeds        : {RESILIENCE_SEEDS[0]}-{RESILIENCE_SEEDS[-1]} "
          f"({len(RESILIENCE_SEEDS)} seeds)")
    print(f"Backbones               : {len(BACKBONES)} "
          f"(PV {PV_SIZES} MW x bat_e {BATTERY_ENERGIES} MWh)\n")

    base_config = _load_config(config_path)
    dataset_path = ROOT / base_config["dataset"]
    data = pd.read_csv(dataset_path)
    n_hours = len(data)
    solver_name = base_config.get("solver", "appsi_highs")

    _run_baseline_guard(data, base_config, solver_name, args.tee)

    scenarios_map = _scenario_by_name(base_config)
    base_bh = scenarios_map["battery_hydrogen"]
    base_db = scenarios_map["diesel_battery"]

    dispatch_cache: dict[tuple, pd.DataFrame] = {}
    lp_counter = [0]

    rows: list[dict[str, Any]] = []
    # Summary data collected per backbone for the final table
    summary_rows: list[dict[str, Any]] = []

    for b_idx, (pv_mw, bat_e_mwh) in enumerate(BACKBONES):
        backbone_id = f"B{b_idx + 1}"
        bat_p_mw = round(bat_e_mwh / BACKBONE_EP_RATIO, 4)

        print(f"{'=' * 66}")
        print(f"Backbone {backbone_id}: PV={pv_mw:.1f} MW  bat_e={bat_e_mwh:.1f} MWh  "
              f"bat_p={bat_p_mw:.4f} MW")
        print(f"{'=' * 66}")

        matched_db = _make_matched_scenario(base_db, pv_mw, bat_e_mwh, bat_p_mw)
        matched_bh = _make_matched_scenario(base_bh, pv_mw, bat_e_mwh, bat_p_mw)

        backbone_cfg = _make_backbone_cfg(base_config, carbon_price)

        # ------ Crossover sweep ------
        n_before = lp_counter[0]
        crossover = _compute_crossover(
            data, matched_bh, matched_db, backbone_cfg,
            dispatch_cache, solver_name, args.tee, lp_counter,
        )
        n_new = lp_counter[0] - n_before
        xo_str = f"{crossover:.1f}" if not pd.isna(crossover) else "NaN"
        print(f"  Crossover: {xo_str} USD/MWh  [{n_new} LP solves, cache total: {len(dispatch_cache)}]")

        # ------ Reference costs at diesel=220 (interpolated) ------
        cfg_lo = copy.deepcopy(backbone_cfg)
        cfg_lo["costs"]["diesel_fuel_usd_per_mwh"] = DIESEL_COST_REF_LOWER  # 200
        cfg_hi = copy.deepcopy(backbone_cfg)
        cfg_hi["costs"]["diesel_fuel_usd_per_mwh"] = DIESEL_COST_REF_UPPER  # 250
        cfg_ref = copy.deepcopy(backbone_cfg)
        cfg_ref["costs"]["diesel_fuel_usd_per_mwh"] = DIESEL_COST_REF  # 220 (for bh)

        ck_db_lo = _dispatch_cache_key(matched_db, cfg_lo)
        ck_db_hi = _dispatch_cache_key(matched_db, cfg_hi)
        ck_bh    = _dispatch_cache_key(matched_bh, cfg_lo)  # diesel-independent

        db_dispatch_lo = dispatch_cache[ck_db_lo]
        db_dispatch_hi = dispatch_cache[ck_db_hi]
        bh_dispatch    = dispatch_cache[ck_bh]

        db_sum_lo = calculate_summary(db_dispatch_lo, matched_db, cfg_lo)
        db_sum_hi = calculate_summary(db_dispatch_hi, matched_db, cfg_hi)

        t = REF_INTERP_T  # 0.4
        db_cost_220  = db_sum_lo["total_annual_cost_usd"]  + t * (db_sum_hi["total_annual_cost_usd"]  - db_sum_lo["total_annual_cost_usd"])
        db_lcoe_220  = db_sum_lo["lcoe_usd_per_mwh_served"] + t * (db_sum_hi["lcoe_usd_per_mwh_served"] - db_sum_lo["lcoe_usd_per_mwh_served"])

        bh_sum = calculate_summary(bh_dispatch, matched_bh, cfg_ref)
        bh_cost_220 = bh_sum["total_annual_cost_usd"]
        bh_lcoe_220 = bh_sum["lcoe_usd_per_mwh_served"]

        delta_cost = bh_cost_220 - db_cost_220
        sign = "+" if delta_cost >= 0 else ""
        print(f"  Cost @ diesel=220:  DB={db_cost_220:>12,.0f}  BH={bh_cost_220:>12,.0f}  "
              f"delta={sign}{delta_cost:,.0f} USD/yr")

        # Annual unmet load (from dispatch at diesel=200)
        db_unmet_mwh = float(db_dispatch_lo["unmet_load_mw"].sum())
        bh_unmet_mwh = float(bh_dispatch["unmet_load_mw"].sum())

        # ------ Resilience across 10 seeds ------
        print(f"  Resilience evaluation ({len(RESILIENCE_SEEDS)} seeds x {OUTAGE_FREQ_PER_YEAR} events x {FIXED_OUTAGE_HOURS:.0f} h)...")
        db_res = _evaluate_resilience_multi_seed(db_dispatch_lo, matched_db, backbone_cfg, n_hours)
        bh_res = _evaluate_resilience_multi_seed(bh_dispatch,    matched_bh, backbone_cfg, n_hours)
        print(f"  DB  clsr_min={db_res['clsr_min']:.4f}  clsr_mean={db_res['clsr_mean']:.4f}"
              f"  surv_min={db_res['survivable_outage_h_min']:.0f}h  eens_max={db_res['eens_max']:.2f} MWh")
        print(f"  BH  clsr_min={bh_res['clsr_min']:.4f}  clsr_mean={bh_res['clsr_mean']:.4f}"
              f"  surv_min={bh_res['survivable_outage_h_min']:.0f}h  eens_max={bh_res['eens_max']:.2f} MWh")

        # ------ Accumulate rows ------
        shared = {
            "backbone_id": backbone_id,
            "backbone_pv_mw": pv_mw,
            "backbone_battery_mwh": bat_e_mwh,
            "backbone_battery_power_mw": bat_p_mw,
            "crossover_diesel_cost_usd_per_mwh": crossover,
            "delta_cost_at_baseline_usd": delta_cost,
            "battery_hydrogen_preferred": bool(delta_cost < 0),
        }
        for scenario_name, cost_220, lcoe_220, unmet, res_dict in [
            ("diesel_battery",  db_cost_220, db_lcoe_220, db_unmet_mwh, db_res),
            ("battery_hydrogen", bh_cost_220, bh_lcoe_220, bh_unmet_mwh, bh_res),
        ]:
            rows.append({
                **shared,
                "scenario": scenario_name,
                "total_annual_cost_usd": cost_220,
                "lcoe_usd_per_mwh_served": lcoe_220,
                "annual_unmet_mwh": unmet,
                **{f"resilience_{k}": v for k, v in res_dict.items()},
            })

        summary_rows.append({
            "id":            backbone_id,
            "pv_mw":         pv_mw,
            "bat_e_mwh":     bat_e_mwh,
            "crossover":     crossover,
            "db_clsr_min":   db_res["clsr_min"],
            "bh_clsr_min":   bh_res["clsr_min"],
            "delta_cost":    delta_cost,
        })

    total_lp = lp_counter[0]
    print(f"\nSweep complete. Total LP solves (sweep): {total_lp}  Cache entries: {len(dispatch_cache)}\n")

    # ------ Save CSV ------
    output = pd.DataFrame(rows)
    # Rename resilience columns to cleaner names
    output = output.rename(columns={
        "resilience_clsr_min":               "clsr_min",
        "resilience_clsr_mean":              "clsr_mean",
        "resilience_eens_max":               "eens_max",
        "resilience_survivable_outage_h_min": "survivable_outage_h_min",
    })
    out_path = results_dir / "matched_backbone.csv"
    output.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")

    # Confirm guarded files untouched
    for fname in GUARDED_FILES:
        p = results_dir / fname
        if p.exists():
            print(f"Preserved (not modified): {p}")

    # ------ Print summary table ------
    print()
    print("MATCHED BACKBONE SUMMARY  (delta_cost = BH - DB at diesel=220 USD/MWh)")
    print("=" * 82)
    print(
        f"  {'ID':>3}  {'PV':>6}  {'Bat':>5}  {'Crossover':>10}"
        f"  {'DB clsr_min':>11}  {'BH clsr_min':>11}  {'Delta Cost (USD/yr)':>20}"
    )
    print(f"  {'':>3}  {'MW':>6}  {'MWh':>5}  {'USD/MWh':>10}"
          f"  {'':>11}  {'':>11}  {'':>20}")
    print("-" * 82)
    for sr in summary_rows:
        xo_str = f"{sr['crossover']:>10.1f}" if not pd.isna(sr["crossover"]) else f"{'NaN':>10}"
        sign = "+" if sr["delta_cost"] >= 0 else ""
        print(
            f"  {sr['id']:>3}  {sr['pv_mw']:>6.1f}  {sr['bat_e_mwh']:>5.1f}  {xo_str}"
            f"  {sr['db_clsr_min']:>11.4f}  {sr['bh_clsr_min']:>11.4f}"
            f"  {sign}{sr['delta_cost']:>19,.0f}"
        )
    print("=" * 82)


if __name__ == "__main__":
    main()
