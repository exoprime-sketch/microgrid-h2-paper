"""E4 diesel-outage robustness: graded diesel-support stress test."""

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

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
# D0-D3 reference: base manuscript conditions (carbon=0, diesel=220)
DIESEL_COST_REF   = 220.0
CARBON_PRICE_REF  = 0.0   # base_config value

# D4 sweep conditions (consistent with E1 headline)
DIESEL_COSTS_D4: list[float] = [round(100.0 + 50.0 * i, 1) for i in range(19)]  # step 50
D4_SHOCK_PRICES: list[float] = [380.0, 500.0, 700.0, 1000.0]
CARBON_PRICE_D4   = 150.0

RESILIENCE_SEEDS: list[int] = list(range(1, 11))
OUTAGE_FREQ    = 4
OUTAGE_DUR_H   = 48.0

BASELINE_EXPECTED: dict[str, float] = {
    "battery_only":    19_239_599.0,
    "diesel_battery":   2_252_545.0,
    "battery_hydrogen": 3_962_313.0,
}
BASELINE_TOL = 0.001

# Resilience regression guard: base-case values after UTC+8 load fix (seed=2025)
RESILIENCE_EXPECTED: dict[str, dict[str, float]] = {
    "battery_only":     {"clsr": 1.000, "eens_mwh": 0.0,  "surv_h": 48.0},
    "diesel_battery":   {"clsr": 0.654, "eens_mwh": 44.3, "surv_h":  1.0},
    "battery_hydrogen": {"clsr": 1.000, "eens_mwh": 0.0,  "surv_h": 48.0},
}
RES_CLSR_TOL = 0.01
RES_EENS_TOL = 0.5
# survivable: int equality

GUARDED_FILES = [
    "crossover_diesel_cost.csv",
    "sensitivity_fine.csv",
    "cost_driver_elasticity.csv",
    "matched_backbone.csv",
]

# D0-D3 cases
ROBUSTNESS_CASES: list[dict[str, Any]] = [
    {"case_type": "D0", "case_label": "unavailable",  "diesel_available": False, "derate": 1.0,  "budget_h": None, "delay_h": 0},
    {"case_type": "D1", "case_label": "derate_25pct", "diesel_available": True,  "derate": 0.25, "budget_h": None, "delay_h": 0},
    {"case_type": "D1", "case_label": "derate_50pct", "diesel_available": True,  "derate": 0.50, "budget_h": None, "delay_h": 0},
    {"case_type": "D1", "case_label": "derate_75pct", "diesel_available": True,  "derate": 0.75, "budget_h": None, "delay_h": 0},
    {"case_type": "D2", "case_label": "fuel_3h",      "diesel_available": True,  "derate": 1.0,  "budget_h":  3,   "delay_h": 0},
    {"case_type": "D2", "case_label": "fuel_6h",      "diesel_available": True,  "derate": 1.0,  "budget_h":  6,   "delay_h": 0},
    {"case_type": "D2", "case_label": "fuel_12h",     "diesel_available": True,  "derate": 1.0,  "budget_h": 12,   "delay_h": 0},
    {"case_type": "D2", "case_label": "fuel_24h",     "diesel_available": True,  "derate": 1.0,  "budget_h": 24,   "delay_h": 0},
    {"case_type": "D3", "case_label": "delay_6h",     "diesel_available": True,  "derate": 1.0,  "budget_h": None, "delay_h":  6},
    {"case_type": "D3", "case_label": "delay_12h",    "diesel_available": True,  "derate": 1.0,  "budget_h": None, "delay_h": 12},
    {"case_type": "D3", "case_label": "delay_24h",    "diesel_available": True,  "derate": 1.0,  "budget_h": None, "delay_h": 24},
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _scenario_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in config["scenarios"]}


def _dispatch_cache_key(scenario: dict[str, Any], cfg: dict[str, Any]) -> tuple:
    if float(scenario.get("diesel_mw", 0.0)) <= 0.0:
        return (scenario["name"], 0.0)
    effective = (
        float(cfg["costs"]["diesel_fuel_usd_per_mwh"])
        + float(cfg["global"].get("carbon_price_usd_per_t", 0.0))
        * float(cfg["global"]["diesel_co2_t_per_mwh"])
    )
    return (scenario["name"], round(effective, 6))


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
    if float(scenario.get("diesel_mw", 0.0)) > 0.0:
        eff = (
            float(case_cfg["costs"]["diesel_fuel_usd_per_mwh"])
            + float(case_cfg["global"].get("carbon_price_usd_per_t", 0.0))
            * float(case_cfg["global"]["diesel_co2_t_per_mwh"])
        )
        info = f"eff_cost={eff:.1f}"
    else:
        info = "no diesel"
    print(f"  [LP SOLVE {lp_counter[0]:>3}]  {scenario['name']:<22}  {info}")
    model = build_dispatch_model(data, scenario, case_cfg)
    solve_dispatch_model(model, solver_name=solver_name, tee=tee)
    dispatch_cache[ck] = extract_dispatch(model, data, scenario)


def _evaluate_resilience_multi_seed(
    dispatch: pd.DataFrame,
    scenario: dict[str, Any],
    config: dict[str, Any],
    n_hours: int,
) -> dict[str, float]:
    clsr_list, eens_list, surv_list = [], [], []
    for seed in RESILIENCE_SEEDS:
        events = generate_outage_events(
            n_hours=n_hours, frequency_per_year=OUTAGE_FREQ,
            duration_hours=OUTAGE_DUR_H, seed=seed,
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


def _make_resilience_cfg(base_config: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy base config and stamp D0-D3 resilience parameters."""
    cfg = copy.deepcopy(base_config)
    res = cfg.setdefault("resilience", {})
    res["diesel_available_during_outage"] = case["diesel_available"]
    res["diesel_derate_fraction"]         = case["derate"]
    res["diesel_delay_h"]                 = case["delay_h"]
    if case["budget_h"] is not None:
        res["diesel_fuel_budget_h"] = float(case["budget_h"])
    else:
        res.pop("diesel_fuel_budget_h", None)   # falls back to default inf
    return cfg


# ------------------------------------------------------------------
# Guards
# ------------------------------------------------------------------
def _run_cost_baseline_guard(
    data: pd.DataFrame,
    base_config: dict[str, Any],
    solver_name: str,
    tee: bool,
    dispatch_cache: dict,
    lp_counter: list[int],
) -> None:
    """Solve base scenarios at base_config, check locked costs, save dispatches to cache."""
    print("=" * 66)
    print("COST BASELINE GUARD")
    print("=" * 66)
    scenarios = _scenario_by_name(base_config)
    errors: list[str] = []
    for name, expected in BASELINE_EXPECTED.items():
        scenario = scenarios[name]
        _maybe_solve(data, scenario, base_config, dispatch_cache, solver_name, tee, lp_counter)
        dispatch = dispatch_cache[_dispatch_cache_key(scenario, base_config)]
        summary = calculate_summary(dispatch, scenario, base_config)
        actual  = float(summary["total_annual_cost_usd"])
        rel_err = abs(actual - expected) / expected
        status  = "PASS" if rel_err <= BASELINE_TOL else "FAIL"
        print(
            f"  {name:<22}  expected={expected:>13,.0f}  "
            f"actual={actual:>13,.0f}  err={rel_err:.4%}  {status}"
        )
        if rel_err > BASELINE_TOL:
            errors.append(f"{name}: {actual:.0f} (err={rel_err:.4%})")
    if errors:
        print("\nCost guard FAILED -- aborting:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print("Cost guard PASSED.\n")


def _run_resilience_regression_guard(
    base_config: dict[str, Any],
    dispatch_cache: dict,
    n_hours: int,
) -> None:
    """Verify additive resilience.py change reproduces original base-case resilience values."""
    print("=" * 66)
    print("RESILIENCE REGRESSION GUARD  (seed=2025, diesel_available=False)")
    print("=" * 66)
    scenarios  = _scenario_by_name(base_config)
    events     = outage_events_from_config(base_config, n_hours)
    errors: list[str] = []
    for name, exp in RESILIENCE_EXPECTED.items():
        scenario = scenarios[name]
        dispatch = dispatch_cache[_dispatch_cache_key(scenario, base_config)]
        res = evaluate_resilience(dispatch, scenario, base_config, events=events)
        a_clsr = float(res["critical_load_served_ratio"])
        a_eens = float(res["eens_mwh"])
        a_surv = float(res["survivable_outage_duration_h"])
        clsr_ok = abs(a_clsr - exp["clsr"])     <= RES_CLSR_TOL
        eens_ok = abs(a_eens - exp["eens_mwh"]) <= RES_EENS_TOL
        surv_ok = int(a_surv) == int(exp["surv_h"])
        status  = "PASS" if (clsr_ok and eens_ok and surv_ok) else "FAIL"
        print(
            f"  {name:<22}  CLSR={a_clsr:.3f}(exp {exp['clsr']:.3f}) {'ok' if clsr_ok else 'FAIL'}"
            f"  EENS={a_eens:.1f}(exp {exp['eens_mwh']:.1f}) {'ok' if eens_ok else 'FAIL'}"
            f"  surv={a_surv:.0f}h(exp {exp['surv_h']:.0f}h) {'ok' if surv_ok else 'FAIL'}"
            f"  {status}"
        )
        if not (clsr_ok and eens_ok and surv_ok):
            errors.append(
                f"{name}: CLSR={a_clsr:.3f}, EENS={a_eens:.1f}, surv={a_surv:.0f}h"
            )
    if errors:
        print("\nResilience regression guard FAILED -- aborting:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print("Resilience regression guard PASSED.\n")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="E4 diesel-outage robustness sweep.")
    parser.add_argument("--config",      type=Path, default=ROOT / "configs" / "scenarios.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--tee",         action="store_true")
    args = parser.parse_args()

    config_path = args.config      if args.config.is_absolute()      else ROOT / args.config
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    for fname in GUARDED_FILES:
        p = results_dir / fname
        if p.exists():
            print(f"Guarded (will not overwrite): {p}")

    print(f"\nD0-D3 reference: diesel={DIESEL_COST_REF:.0f} USD/MWh, carbon={CARBON_PRICE_REF:.0f} USD/tCO2")
    print(f"D4 sweep:        carbon={CARBON_PRICE_D4:.0f} USD/tCO2, "
          f"diesel={DIESEL_COSTS_D4[0]:.0f}-{DIESEL_COSTS_D4[-1]:.0f} step 50 "
          f"({len(DIESEL_COSTS_D4)} levels)")
    print(f"Resilience seeds: {RESILIENCE_SEEDS[0]}-{RESILIENCE_SEEDS[-1]}, "
          f"{OUTAGE_FREQ} events/yr, {OUTAGE_DUR_H:.0f} h\n")

    base_config = _load_config(config_path)
    dataset_path = ROOT / base_config["dataset"]
    data = pd.read_csv(dataset_path)
    n_hours = len(data)
    solver_name = base_config.get("solver", "appsi_highs")

    # Shared dispatch cache
    dispatch_cache: dict[tuple, pd.DataFrame] = {}
    lp_counter = [0]

    # ----------------------------------------------------------------
    # Phase 1 & 2: Guards — cost guard saves dispatches used by regression guard
    # ----------------------------------------------------------------
    _run_cost_baseline_guard(data, base_config, solver_name, args.tee, dispatch_cache, lp_counter)
    _run_resilience_regression_guard(base_config, dispatch_cache, n_hours)

    scenarios_map = _scenario_by_name(base_config)
    db_scenario   = scenarios_map["diesel_battery"]
    bh_scenario   = scenarios_map["battery_hydrogen"]

    # Dispatches at base conditions (from cost guard)
    db_ref_dispatch = dispatch_cache[_dispatch_cache_key(db_scenario, base_config)]
    bh_ref_dispatch = dispatch_cache[_dispatch_cache_key(bh_scenario, base_config)]

    # Annual costs at base conditions
    db_ref_cost = float(calculate_summary(db_ref_dispatch, db_scenario, base_config)["total_annual_cost_usd"])
    bh_ref_cost = float(calculate_summary(bh_ref_dispatch, bh_scenario, base_config)["total_annual_cost_usd"])
    print(f"Base costs (carbon=0, diesel=220): DB={db_ref_cost:,.0f}  BH={bh_ref_cost:,.0f}  "
          f"delta={bh_ref_cost-db_ref_cost:+,.0f}\n")

    # ----------------------------------------------------------------
    # Phase 3: D0-D3 resilience evaluation (0 LP solves)
    # ----------------------------------------------------------------
    print("D0-D3 resilience sweeps (no LP, using base dispatch at diesel=220, carbon=0)...")
    rows: list[dict[str, Any]] = []
    d0d3_summary: list[dict[str, Any]] = []

    for case in ROBUSTNESS_CASES:
        res_cfg = _make_resilience_cfg(base_config, case)
        db_res  = _evaluate_resilience_multi_seed(db_ref_dispatch, db_scenario, res_cfg, n_hours)
        bh_res  = _evaluate_resilience_multi_seed(bh_ref_dispatch, bh_scenario, res_cfg, n_hours)

        for scen_name, cost, res in [
            (db_scenario["name"], db_ref_cost, db_res),
            (bh_scenario["name"], bh_ref_cost, bh_res),
        ]:
            rows.append({
                "case_type":                         case["case_type"],
                "case_label":                        case["case_label"],
                "scenario":                          scen_name,
                "diesel_available_during_outage":    case["diesel_available"],
                "diesel_derate_fraction":            case["derate"],
                "diesel_fuel_budget_h":              float(case["budget_h"]) if case["budget_h"] else float("inf"),
                "diesel_delay_h":                    case["delay_h"],
                "delivered_diesel_cost_usd_per_mwh": DIESEL_COST_REF,
                "carbon_price_usd_per_t":            CARBON_PRICE_REF,
                "total_annual_cost_usd":             cost,
                "delta_cost_usd":                    bh_ref_cost - db_ref_cost,
                **res,
            })

        d0d3_summary.append({
            "case_type":  case["case_type"],
            "case_label": case["case_label"],
            "db_surv_min": db_res["survivable_outage_h_min"],
            "db_clsr_min": db_res["clsr_min"],
            "db_eens_max": db_res["eens_max"],
        })

    print(f"  Done: {len(ROBUSTNESS_CASES) * len(RESILIENCE_SEEDS) * 2} evaluate_resilience calls, 0 LP solves.")

    # ----------------------------------------------------------------
    # Phase 4: D4 sweep (19 LP solves for diesel_battery, carbon=150)
    # ----------------------------------------------------------------
    print(f"\nD4 annual-cost sweep (carbon={CARBON_PRICE_D4:.0f}, {len(DIESEL_COSTS_D4)} diesel levels)...")
    d4_base_cfg = copy.deepcopy(base_config)
    d4_base_cfg["global"]["carbon_price_usd_per_t"] = CARBON_PRICE_D4

    d4_db_annual_costs: list[float] = []
    d4_bh_annual_cost  = float(
        calculate_summary(bh_ref_dispatch, bh_scenario, d4_base_cfg)["total_annual_cost_usd"]
    )
    d4_deltas: list[float] = []

    for diesel_cost in DIESEL_COSTS_D4:
        case_cfg = copy.deepcopy(d4_base_cfg)
        case_cfg["costs"]["diesel_fuel_usd_per_mwh"] = diesel_cost
        _maybe_solve(data, db_scenario, case_cfg, dispatch_cache, solver_name, args.tee, lp_counter)
        db_d = dispatch_cache[_dispatch_cache_key(db_scenario, case_cfg)]
        db_c = float(calculate_summary(db_d, db_scenario, case_cfg)["total_annual_cost_usd"])
        d4_db_annual_costs.append(db_c)
        d4_deltas.append(d4_bh_annual_cost - db_c)

    d4_crossover = _interpolate_crossover(np.array(DIESEL_COSTS_D4), np.array(d4_deltas))
    print(f"  D4 crossover (carbon=150): {d4_crossover:.1f} USD/MWh  (cf. E1 baseline ~376.9)")

    # D4 shock-price rows (4 prices x 2 scenarios)
    print(f"\nD4 shock-price resilience ({len(D4_SHOCK_PRICES)} prices x 10 seeds)...")
    for shock_price in D4_SHOCK_PRICES:
        # Annual cost: interpolate if shock_price not on step-50 grid
        if shock_price in DIESEL_COSTS_D4:
            idx = DIESEL_COSTS_D4.index(shock_price)
            db_cost_shock = d4_db_annual_costs[idx]
        else:
            lo = max(i for i, c in enumerate(DIESEL_COSTS_D4) if c < shock_price)
            hi = lo + 1
            t  = (shock_price - DIESEL_COSTS_D4[lo]) / (DIESEL_COSTS_D4[hi] - DIESEL_COSTS_D4[lo])
            db_cost_shock = d4_db_annual_costs[lo] + t * (d4_db_annual_costs[hi] - d4_db_annual_costs[lo])
            dispatch_diesel_cost = DIESEL_COSTS_D4[hi]  # nearest step-50 ≥ shock for dispatch
        dispatch_diesel_cost = (
            shock_price if shock_price in DIESEL_COSTS_D4
            else min(DIESEL_COSTS_D4, key=lambda c: (abs(c - shock_price), c))
        )

        # Resilience (diesel fully available, D4)
        d4_res_cfg = copy.deepcopy(d4_base_cfg)
        d4_res_cfg["costs"]["diesel_fuel_usd_per_mwh"] = dispatch_diesel_cost
        d4_res_cfg["resilience"]["diesel_available_during_outage"] = True

        db_dispatch_shock = dispatch_cache[_dispatch_cache_key(db_scenario, d4_res_cfg)]
        db_res_d4 = _evaluate_resilience_multi_seed(db_dispatch_shock, db_scenario, d4_res_cfg, n_hours)
        bh_res_d4 = _evaluate_resilience_multi_seed(bh_ref_dispatch,    bh_scenario,  d4_res_cfg, n_hours)
        delta_shock = d4_bh_annual_cost - db_cost_shock

        for scen_name, cost, res in [
            (db_scenario["name"], db_cost_shock,  db_res_d4),
            (bh_scenario["name"], d4_bh_annual_cost, bh_res_d4),
        ]:
            rows.append({
                "case_type":                         "D4",
                "case_label":                        f"shock_{int(shock_price)}",
                "scenario":                          scen_name,
                "diesel_available_during_outage":    True,
                "diesel_derate_fraction":            1.0,
                "diesel_fuel_budget_h":              float("inf"),
                "diesel_delay_h":                    0,
                "delivered_diesel_cost_usd_per_mwh": shock_price,
                "carbon_price_usd_per_t":            CARBON_PRICE_D4,
                "total_annual_cost_usd":             cost,
                "delta_cost_usd":                    delta_shock,
                **res,
            })

    total_lp = lp_counter[0]
    print(f"\nSweep complete. Total LP solves: {total_lp}  Cache entries: {len(dispatch_cache)}\n")

    # ----------------------------------------------------------------
    # Save CSV
    # ----------------------------------------------------------------
    output = pd.DataFrame(rows)
    out_path = results_dir / "outage_robustness.csv"
    output.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")

    # Confirm guarded files untouched
    for fname in GUARDED_FILES:
        p = results_dir / fname
        if p.exists():
            print(f"Preserved (not modified): {p}")

    # Also store D4 full sweep for plotting (not a separate file — embed as metadata attribute)
    # Write a companion CSV for the figure's smooth cost line
    d4_sweep_path = results_dir / "outage_robustness_d4_sweep.csv"
    pd.DataFrame({
        "delivered_diesel_cost_usd_per_mwh": DIESEL_COSTS_D4,
        "db_total_annual_cost_usd":          d4_db_annual_costs,
        "bh_total_annual_cost_usd":          [d4_bh_annual_cost] * len(DIESEL_COSTS_D4),
        "delta_cost_usd":                    d4_deltas,
        "carbon_price_usd_per_t":            [CARBON_PRICE_D4] * len(DIESEL_COSTS_D4),
    }).to_csv(d4_sweep_path, index=False)
    print(f"Wrote {d4_sweep_path}  (D4 full cost curve for fig06 right panel)")

    # ----------------------------------------------------------------
    # Print D0-D3 summary table
    # ----------------------------------------------------------------
    print()
    print("D0-D3 RESILIENCE SUMMARY  (diesel_battery, 10 seeds x 48-h/4-event outages)")
    print(f"  Battery-hydrogen reference: surv_min=48h, clsr_min=1.0000 (invariant)")
    print("=" * 68)
    print(f"  {'Type':<4}  {'Label':<14}  {'surv_min (h)':>12}  {'clsr_min':>9}  {'eens_max (MWh)':>15}")
    print("-" * 68)
    for sr in d0d3_summary:
        print(
            f"  {sr['case_type']:<4}  {sr['case_label']:<14}  "
            f"{sr['db_surv_min']:>12.0f}  {sr['db_clsr_min']:>9.4f}  "
            f"{sr['db_eens_max']:>15.2f}"
        )
    print("=" * 68)


if __name__ == "__main__":
    main()
