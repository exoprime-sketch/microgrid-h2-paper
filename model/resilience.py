"""Outage resilience post-processing for fixed-capacity portfolios."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _scenario_float(scenario: dict[str, Any], key: str) -> float:
    return float(scenario.get(key, 0.0))


def generate_outage_events(
    n_hours: int,
    frequency_per_year: int | float,
    duration_hours: int | float,
    seed: int = 123,
) -> pd.DataFrame:
    """Generate reproducible random outage starts for an 8760-hour year."""

    count = int(round(float(frequency_per_year)))
    duration = int(round(float(duration_hours)))
    if count <= 0 or duration <= 0:
        return pd.DataFrame(columns=["event_id", "start_hour", "duration_hours"])
    rng = np.random.default_rng(seed)
    starts = sorted(int(item) for item in rng.integers(0, n_hours, size=count))
    return pd.DataFrame(
        {
            "event_id": list(range(1, count + 1)),
            "start_hour": starts,
            "duration_hours": [duration] * count,
        }
    )


def outage_events_from_config(
    config: dict[str, Any], n_hours: int, duration_hours: float | None = None
) -> pd.DataFrame:
    resilience = config.get("resilience", {})
    return generate_outage_events(
        n_hours=n_hours,
        frequency_per_year=resilience.get("outage_frequency_per_year", 0),
        duration_hours=(
            duration_hours
            if duration_hours is not None
            else resilience.get("outage_duration_hours", 0)
        ),
        seed=int(resilience.get("random_seed", 123)),
    )


def add_event_timestamps(events: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    output = events.copy()
    parsed = pd.to_datetime(timestamps).reset_index(drop=True)
    output["start_timestamp"] = [parsed.iloc[int(hour) % len(parsed)] for hour in output["start_hour"]]
    return output


def _initial_state(
    dispatch: pd.DataFrame,
    start_hour: int,
    battery_energy_mwh: float,
    h2_tank_kg: float,
    initial_battery_soc_fraction: float,
    initial_h2_inventory_fraction: float,
) -> tuple[float, float]:
    previous_hour = (start_hour - 1) % len(dispatch)
    if battery_energy_mwh > 0.0 and "battery_soc_mwh" in dispatch:
        battery_soc = float(dispatch.loc[previous_hour, "battery_soc_mwh"])
    else:
        battery_soc = battery_energy_mwh * initial_battery_soc_fraction
    if h2_tank_kg > 0.0 and "h2_inventory_kg" in dispatch:
        h2_inventory = float(dispatch.loc[previous_hour, "h2_inventory_kg"])
    else:
        h2_inventory = h2_tank_kg * initial_h2_inventory_fraction
    return battery_soc, h2_inventory


def _simulate_single_outage(
    dispatch: pd.DataFrame,
    scenario: dict[str, Any],
    config: dict[str, Any],
    start_hour: int,
    duration_hours: int,
) -> dict[str, float]:
    defaults = config["defaults"]
    resilience = config.get("resilience", {})

    critical_fraction = float(resilience.get("critical_load_fraction", 0.5))
    diesel_available = bool(resilience.get("diesel_available_during_outage", False))

    battery_power_mw = _scenario_float(scenario, "battery_power_mw")
    battery_energy_mwh = _scenario_float(scenario, "battery_energy_mwh")
    diesel_mw = _scenario_float(scenario, "diesel_mw")
    # D1/D2/D3 optional parameters — all default to original behaviour when absent
    diesel_derate        = float(resilience.get("diesel_derate_fraction", 1.0))
    diesel_budget_mwh    = float(resilience.get("diesel_fuel_budget_h", float("inf"))) * diesel_mw
    diesel_delay_h       = int(resilience.get("diesel_delay_h", 0))
    diesel_fuel_used_mwh = 0.0
    electrolyzer_mw = _scenario_float(scenario, "electrolyzer_mw")
    fuel_cell_mw = _scenario_float(scenario, "fuel_cell_mw")
    h2_tank_kg = _scenario_float(scenario, "h2_tank_kg")

    battery_charge_eff = float(defaults["battery_charge_efficiency"])
    battery_discharge_eff = float(defaults["battery_discharge_efficiency"])
    electrolyzer_eff = float(defaults["electrolyzer_efficiency_lhv"])
    fuel_cell_eff = float(defaults["fuel_cell_efficiency_lhv"])
    h2_lhv_kwh_per_kg = float(defaults["h2_lhv_kwh_per_kg"])
    initial_soc_fraction = float(defaults["initial_battery_soc_fraction"])
    initial_h2_fraction = float(defaults["initial_h2_inventory_fraction"])

    h2_kg_per_mwh_electrolysis = 1000.0 * electrolyzer_eff / h2_lhv_kwh_per_kg
    h2_kg_per_mwh_fuel_cell = 1000.0 / (fuel_cell_eff * h2_lhv_kwh_per_kg)

    battery_soc, h2_inventory = _initial_state(
        dispatch,
        start_hour,
        battery_energy_mwh,
        h2_tank_kg,
        initial_soc_fraction,
        initial_h2_fraction,
    )

    critical_load_mwh = 0.0
    served_mwh = 0.0
    unserved_mwh = 0.0
    loss_hours = 0
    survivable_hours = duration_hours
    failed = False

    for offset in range(duration_hours):
        hour = (start_hour + offset) % len(dispatch)
        critical_load = critical_fraction * float(dispatch.loc[hour, "load_mw"])
        pv_available = float(dispatch.loc[hour, "pv_available_mw"])
        critical_load_mwh += critical_load

        served_by_pv = min(pv_available, critical_load)
        remaining_load = critical_load - served_by_pv
        excess_pv = max(0.0, pv_available - served_by_pv)

        if remaining_load > 0.0 and battery_power_mw > 0.0 and battery_soc > 0.0:
            battery_delivery = min(
                remaining_load,
                battery_power_mw,
                battery_soc * battery_discharge_eff,
            )
            battery_soc -= battery_delivery / battery_discharge_eff
            remaining_load -= battery_delivery

        if remaining_load > 0.0 and fuel_cell_mw > 0.0 and h2_inventory > 0.0:
            fuel_cell_delivery = min(
                remaining_load,
                fuel_cell_mw,
                h2_inventory / h2_kg_per_mwh_fuel_cell,
            )
            h2_inventory -= fuel_cell_delivery * h2_kg_per_mwh_fuel_cell
            remaining_load -= fuel_cell_delivery

        effective_diesel_mw = diesel_mw * diesel_derate
        diesel_ready = diesel_available and (offset >= diesel_delay_h)
        fuel_remaining = diesel_budget_mwh - diesel_fuel_used_mwh
        if remaining_load > 0.0 and diesel_ready and effective_diesel_mw > 0.0 and fuel_remaining > 1e-9:
            diesel_delivery = min(remaining_load, effective_diesel_mw, fuel_remaining)
            remaining_load -= diesel_delivery
            diesel_fuel_used_mwh += diesel_delivery

        hour_unserved = max(0.0, remaining_load)
        if hour_unserved > 1.0e-7:
            loss_hours += 1
            if not failed:
                survivable_hours = offset
                failed = True

        served_mwh += critical_load - hour_unserved
        unserved_mwh += hour_unserved

        if excess_pv > 0.0 and battery_power_mw > 0.0 and battery_energy_mwh > 0.0:
            battery_charge = min(
                excess_pv,
                battery_power_mw,
                (battery_energy_mwh - battery_soc) / battery_charge_eff,
            )
            battery_soc += battery_charge * battery_charge_eff
            excess_pv -= battery_charge

        if excess_pv > 0.0 and electrolyzer_mw > 0.0 and h2_tank_kg > 0.0:
            electrolyzer_power = min(
                excess_pv,
                electrolyzer_mw,
                (h2_tank_kg - h2_inventory) / h2_kg_per_mwh_electrolysis,
            )
            h2_inventory += electrolyzer_power * h2_kg_per_mwh_electrolysis

        battery_soc = min(max(battery_soc, 0.0), battery_energy_mwh)
        h2_inventory = min(max(h2_inventory, 0.0), h2_tank_kg)

    return {
        "critical_load_mwh": critical_load_mwh,
        "critical_load_served_mwh": served_mwh,
        "eens_mwh": unserved_mwh,
        "loss_of_load_hours": float(loss_hours),
        "survivable_outage_duration_h": float(survivable_hours),
    }


def evaluate_resilience(
    dispatch: pd.DataFrame,
    scenario: dict[str, Any],
    config: dict[str, Any],
    events: pd.DataFrame | None = None,
) -> dict[str, float | str]:
    """Evaluate critical-load resilience for configured random outage events."""

    resilience = config.get("resilience", {})
    if events is None:
        events = outage_events_from_config(config, len(dispatch))

    if events.empty:
        return {
            "scenario": scenario["name"],
            "outage_event_count": 0,
            "outage_duration_hours": 0.0,
            "critical_load_fraction": float(resilience.get("critical_load_fraction", 0.0)),
            "critical_load_mwh": 0.0,
            "critical_load_served_mwh": 0.0,
            "critical_load_served_ratio": 1.0,
            "lpsp": 0.0,
            "eens_mwh": 0.0,
            "loss_of_load_hours": 0.0,
            "survivable_outage_duration_h": 0.0,
            "survivable_outage_duration_h_mean": 0.0,
        }

    event_results = [
        _simulate_single_outage(
            dispatch=dispatch,
            scenario=scenario,
            config=config,
            start_hour=int(row.start_hour),
            duration_hours=int(row.duration_hours),
        )
        for row in events.itertuples(index=False)
    ]

    critical_load_mwh = sum(item["critical_load_mwh"] for item in event_results)
    served_mwh = sum(item["critical_load_served_mwh"] for item in event_results)
    eens_mwh = sum(item["eens_mwh"] for item in event_results)
    survivable = [item["survivable_outage_duration_h"] for item in event_results]

    return {
        "scenario": scenario["name"],
        "outage_event_count": int(len(events)),
        "outage_duration_hours": float(events["duration_hours"].iloc[0]),
        "critical_load_fraction": float(resilience.get("critical_load_fraction", 0.0)),
        "critical_load_mwh": critical_load_mwh,
        "critical_load_served_mwh": served_mwh,
        "critical_load_served_ratio": served_mwh / critical_load_mwh if critical_load_mwh else 1.0,
        "lpsp": eens_mwh / critical_load_mwh if critical_load_mwh else 0.0,
        "eens_mwh": eens_mwh,
        "loss_of_load_hours": sum(item["loss_of_load_hours"] for item in event_results),
        "survivable_outage_duration_h": min(survivable) if survivable else 0.0,
        "survivable_outage_duration_h_mean": float(np.mean(survivable)) if survivable else 0.0,
    }
