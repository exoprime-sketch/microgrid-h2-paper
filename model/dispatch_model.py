"""Linear hourly dispatch model for simple island microgrid comparisons.

The model intentionally keeps capacities fixed by scenario. This makes the
baseline transparent and leaves capacity expansion, outage modeling, and
resilience metrics as straightforward later additions.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from pyomo.environ import (
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    SolverFactory,
    Var,
    minimize,
    value,
)
from pyomo.opt import TerminationCondition

REQUIRED_DATA_COLUMNS = {"timestamp", "load_mw", "pv_capacity_factor"}


def _scenario_float(scenario: dict[str, Any], key: str) -> float:
    return float(scenario.get(key, 0.0))


def _annualization_factor(discount_rate: float, project_life_years: int) -> float:
    if project_life_years <= 0:
        raise ValueError("project_life_years must be positive.")
    if math.isclose(discount_rate, 0.0):
        return 1.0 / project_life_years
    r = discount_rate
    n = project_life_years
    return r * (1.0 + r) ** n / ((1.0 + r) ** n - 1.0)


def validate_input_data(data: pd.DataFrame) -> None:
    missing = REQUIRED_DATA_COLUMNS.difference(data.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Input data is missing required columns: {missing_text}")
    if len(data) != 8760:
        raise ValueError(f"Expected 8760 hourly rows, found {len(data)}.")
    if data["load_mw"].lt(0).any():
        raise ValueError("load_mw must be nonnegative.")
    if data["pv_capacity_factor"].lt(0).any() or data["pv_capacity_factor"].gt(1).any():
        raise ValueError("pv_capacity_factor must be between 0 and 1.")


def build_dispatch_model(
    data: pd.DataFrame, scenario: dict[str, Any], config: dict[str, Any]
) -> ConcreteModel:
    """Build a fixed-capacity hourly dispatch LP for one scenario."""

    validate_input_data(data)
    defaults = config["defaults"]
    costs = config["costs"]
    global_config = config["global"]

    data = data.reset_index(drop=True)
    periods = range(len(data))

    pv_mw = _scenario_float(scenario, "pv_mw")
    battery_power_mw = _scenario_float(scenario, "battery_power_mw")
    battery_energy_mwh = _scenario_float(scenario, "battery_energy_mwh")
    diesel_mw = _scenario_float(scenario, "diesel_mw")
    electrolyzer_mw = _scenario_float(scenario, "electrolyzer_mw")
    fuel_cell_mw = _scenario_float(scenario, "fuel_cell_mw")
    h2_tank_kg = _scenario_float(scenario, "h2_tank_kg")

    battery_charge_eff = float(defaults["battery_charge_efficiency"])
    battery_discharge_eff = float(defaults["battery_discharge_efficiency"])
    initial_soc = battery_energy_mwh * float(defaults["initial_battery_soc_fraction"])
    electrolyzer_eff = float(defaults["electrolyzer_efficiency_lhv"])
    fuel_cell_eff = float(defaults["fuel_cell_efficiency_lhv"])
    h2_lhv_kwh_per_kg = float(defaults["h2_lhv_kwh_per_kg"])
    initial_h2_kg = h2_tank_kg * float(defaults["initial_h2_inventory_fraction"])

    h2_kg_per_mwh_electrolysis = 1000.0 * electrolyzer_eff / h2_lhv_kwh_per_kg
    h2_kg_per_mwh_fuel_cell = 1000.0 / (fuel_cell_eff * h2_lhv_kwh_per_kg)

    demand = dict(enumerate(data["load_mw"].astype(float).to_list()))
    pv_available = {
        t: pv_mw * float(data.loc[t, "pv_capacity_factor"]) for t in periods
    }

    model = ConcreteModel(name=f"dispatch_{scenario['name']}")
    model.T = RangeSet(0, len(data) - 1)
    model.demand = Param(model.T, initialize=demand)
    model.pv_available = Param(model.T, initialize=pv_available)

    model.pv_used = Var(model.T, within=NonNegativeReals)
    model.pv_curtail = Var(model.T, within=NonNegativeReals)
    model.diesel_power = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, diesel_mw)
    )
    model.battery_charge = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, battery_power_mw)
    )
    model.battery_discharge = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, battery_power_mw)
    )
    model.battery_soc = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, battery_energy_mwh)
    )
    model.electrolyzer_power = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, electrolyzer_mw)
    )
    model.fuel_cell_power = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, fuel_cell_mw)
    )
    model.h2_inventory = Var(
        model.T, within=NonNegativeReals, bounds=(0.0, h2_tank_kg)
    )
    model.unmet_load = Var(model.T, within=NonNegativeReals)

    def pv_allocation_rule(m: ConcreteModel, t: int):
        return m.pv_used[t] + m.pv_curtail[t] == m.pv_available[t]

    model.pv_allocation = Constraint(model.T, rule=pv_allocation_rule)

    def power_balance_rule(m: ConcreteModel, t: int):
        supply = (
            m.pv_used[t]
            + m.diesel_power[t]
            + m.battery_discharge[t]
            + m.fuel_cell_power[t]
            + m.unmet_load[t]
        )
        flexible_demand = m.battery_charge[t] + m.electrolyzer_power[t]
        return supply == m.demand[t] + flexible_demand

    model.power_balance = Constraint(model.T, rule=power_balance_rule)

    def battery_soc_rule(m: ConcreteModel, t: int):
        previous_soc = initial_soc if t == 0 else m.battery_soc[t - 1]
        return (
            m.battery_soc[t]
            == previous_soc
            + battery_charge_eff * m.battery_charge[t]
            - m.battery_discharge[t] / battery_discharge_eff
        )

    model.battery_soc_balance = Constraint(model.T, rule=battery_soc_rule)
    model.battery_cyclic = Constraint(expr=model.battery_soc[len(data) - 1] == initial_soc)

    def h2_inventory_rule(m: ConcreteModel, t: int):
        previous_h2 = initial_h2_kg if t == 0 else m.h2_inventory[t - 1]
        return (
            m.h2_inventory[t]
            == previous_h2
            + h2_kg_per_mwh_electrolysis * m.electrolyzer_power[t]
            - h2_kg_per_mwh_fuel_cell * m.fuel_cell_power[t]
        )

    model.h2_inventory_balance = Constraint(model.T, rule=h2_inventory_rule)
    model.h2_cyclic = Constraint(expr=model.h2_inventory[len(data) - 1] == initial_h2_kg)

    diesel_variable_cost_usd_per_mwh = (
        float(costs["diesel_fuel_usd_per_mwh"])
        + float(global_config.get("carbon_price_usd_per_t", 0.0))
        * float(global_config["diesel_co2_t_per_mwh"])
    )

    def objective_rule(m: ConcreteModel):
        return sum(
            diesel_variable_cost_usd_per_mwh * m.diesel_power[t]
            + costs["battery_throughput_usd_per_mwh"]
            * (m.battery_charge[t] + m.battery_discharge[t])
            + costs["electrolyzer_variable_usd_per_mwh"] * m.electrolyzer_power[t]
            + costs["fuel_cell_variable_usd_per_mwh"] * m.fuel_cell_power[t]
            + global_config["unmet_load_penalty_usd_per_mwh"] * m.unmet_load[t]
            for t in m.T
        )

    model.operating_cost = Objective(rule=objective_rule, sense=minimize)
    return model


def solve_dispatch_model(
    model: ConcreteModel, solver_name: str = "appsi_highs", tee: bool = False
):
    """Solve a dispatch model with Pyomo and HiGHS."""

    solver = SolverFactory(solver_name)
    if not solver.available(False):
        raise RuntimeError(f"Pyomo solver '{solver_name}' is not available.")
    results = solver.solve(model, tee=tee)
    termination = results.solver.termination_condition
    if termination != TerminationCondition.optimal:
        raise RuntimeError(f"Solver did not terminate optimally: {termination}")
    return results


def extract_dispatch(
    model: ConcreteModel, data: pd.DataFrame, scenario: dict[str, Any]
) -> pd.DataFrame:
    """Extract hourly dispatch variables to a tidy DataFrame."""

    rows: list[dict[str, Any]] = []
    for t in model.T:
        rows.append(
            {
                "timestamp": data.loc[int(t), "timestamp"],
                "scenario": scenario["name"],
                "load_mw": value(model.demand[t]),
                "pv_available_mw": value(model.pv_available[t]),
                "pv_used_mw": value(model.pv_used[t]),
                "pv_curtail_mw": value(model.pv_curtail[t]),
                "diesel_mw": value(model.diesel_power[t]),
                "battery_charge_mw": value(model.battery_charge[t]),
                "battery_discharge_mw": value(model.battery_discharge[t]),
                "battery_soc_mwh": value(model.battery_soc[t]),
                "electrolyzer_mw": value(model.electrolyzer_power[t]),
                "fuel_cell_mw": value(model.fuel_cell_power[t]),
                "h2_inventory_kg": value(model.h2_inventory[t]),
                "unmet_load_mw": value(model.unmet_load[t]),
            }
        )
    return pd.DataFrame(rows)


def annualized_capital_cost(
    scenario: dict[str, Any], config: dict[str, Any]
) -> tuple[float, float]:
    """Return total overnight CAPEX and equivalent annual capital cost."""

    costs = config["costs"]
    capex_usd = (
        _scenario_float(scenario, "pv_mw") * 1000.0 * costs["pv_usd_per_kw"]
        + _scenario_float(scenario, "battery_power_mw")
        * 1000.0
        * costs["battery_power_usd_per_kw"]
        + _scenario_float(scenario, "battery_energy_mwh")
        * 1000.0
        * costs["battery_energy_usd_per_kwh"]
        + _scenario_float(scenario, "diesel_mw") * 1000.0 * costs["diesel_usd_per_kw"]
        + _scenario_float(scenario, "electrolyzer_mw")
        * 1000.0
        * costs["electrolyzer_usd_per_kw"]
        + _scenario_float(scenario, "fuel_cell_mw")
        * 1000.0
        * costs["fuel_cell_usd_per_kw"]
        + _scenario_float(scenario, "h2_tank_kg") * costs["h2_tank_usd_per_kg"]
    )
    factor = _annualization_factor(
        float(config["global"]["discount_rate"]),
        int(config["global"]["project_life_years"]),
    )
    return capex_usd, capex_usd * factor


def calculate_summary(
    dispatch: pd.DataFrame, scenario: dict[str, Any], config: dict[str, Any]
) -> dict[str, float | str]:
    """Calculate annual cost, reliability, and emission metrics."""

    costs = config["costs"]
    global_config = config["global"]

    capex_usd, annualized_capex_usd = annualized_capital_cost(scenario, config)
    fixed_om_usd = capex_usd * costs["fixed_om_fraction_of_capex"]

    load_mwh = dispatch["load_mw"].sum()
    unmet_mwh = dispatch["unmet_load_mw"].sum()
    served_mwh = load_mwh - unmet_mwh
    diesel_mwh = dispatch["diesel_mw"].sum()
    battery_throughput_mwh = (
        dispatch["battery_charge_mw"].sum() + dispatch["battery_discharge_mw"].sum()
    )
    electrolyzer_mwh = dispatch["electrolyzer_mw"].sum()
    fuel_cell_mwh = dispatch["fuel_cell_mw"].sum()

    diesel_co2_t = diesel_mwh * global_config["diesel_co2_t_per_mwh"]
    carbon_cost_usd = diesel_co2_t * float(global_config.get("carbon_price_usd_per_t", 0.0))
    diesel_fuel_usd = diesel_mwh * costs["diesel_fuel_usd_per_mwh"]
    variable_om_usd = (
        battery_throughput_mwh * costs["battery_throughput_usd_per_mwh"]
        + electrolyzer_mwh * costs["electrolyzer_variable_usd_per_mwh"]
        + fuel_cell_mwh * costs["fuel_cell_variable_usd_per_mwh"]
    )
    unmet_penalty_usd = unmet_mwh * global_config["unmet_load_penalty_usd_per_mwh"]
    total_annual_cost_usd = (
        annualized_capex_usd
        + fixed_om_usd
        + diesel_fuel_usd
        + carbon_cost_usd
        + variable_om_usd
        + unmet_penalty_usd
    )

    return {
        "scenario": scenario["name"],
        "label": scenario.get("label", scenario["name"]),
        "load_mwh": load_mwh,
        "served_mwh": served_mwh,
        "unmet_mwh": unmet_mwh,
        "unmet_fraction": unmet_mwh / load_mwh if load_mwh else 0.0,
        "pv_available_mwh": dispatch["pv_available_mw"].sum(),
        "pv_used_mwh": dispatch["pv_used_mw"].sum(),
        "pv_curtail_mwh": dispatch["pv_curtail_mw"].sum(),
        "diesel_mwh": diesel_mwh,
        "battery_throughput_mwh": battery_throughput_mwh,
        "electrolyzer_mwh": electrolyzer_mwh,
        "fuel_cell_mwh": fuel_cell_mwh,
        "capex_usd": capex_usd,
        "annualized_capital_usd": annualized_capex_usd,
        "fixed_om_usd": fixed_om_usd,
        "diesel_fuel_usd": diesel_fuel_usd,
        "carbon_cost_usd": carbon_cost_usd,
        "variable_om_usd": variable_om_usd,
        "unmet_load_penalty_usd": unmet_penalty_usd,
        "total_annual_cost_usd": total_annual_cost_usd,
        "lcoe_usd_per_mwh_served": (
            total_annual_cost_usd / served_mwh if served_mwh > 0.0 else math.nan
        ),
        "diesel_co2_t": diesel_co2_t,
        "carbon_price_usd_per_t": float(global_config.get("carbon_price_usd_per_t", 0.0)),
    }
