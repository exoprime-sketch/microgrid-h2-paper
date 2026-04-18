"""Calibrated hourly load archetypes for island case studies.

The functions in this module keep the original reproducible synthetic load
idea, but expose the assumptions that usually need to be calibrated for an
ASEAN off-grid case study.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_hourly_timestamps(year: int) -> pd.DatetimeIndex:
    """Return an 8760-hour non-leap timestamp index."""

    start = pd.Timestamp(f"{year}-01-01 00:00:00")
    end = pd.Timestamp(f"{year + 1}-01-01 00:00:00")
    if int((end - start).total_seconds() // 3600) != 8760:
        raise ValueError(f"{year} is a leap year; use a non-leap 8760-hour analysis year.")
    timestamps = pd.date_range(f"{year}-01-01 00:00:00", periods=8760, freq="h")
    return timestamps


def _monthly_multipliers(
    timestamps: pd.DatetimeIndex, multiplier: float | list[float] | dict[str, float] | None
) -> np.ndarray:
    if multiplier is None:
        return np.ones(len(timestamps))
    if isinstance(multiplier, int | float):
        return np.full(len(timestamps), float(multiplier))
    if isinstance(multiplier, list):
        if len(multiplier) != 12:
            raise ValueError("seasonal_multiplier lists must contain 12 monthly values.")
        values = {month: float(multiplier[month - 1]) for month in range(1, 13)}
    elif isinstance(multiplier, dict):
        values = {int(month): float(value) for month, value in multiplier.items()}
        missing = sorted(set(range(1, 13)).difference(values))
        if missing:
            raise ValueError(f"seasonal_multiplier is missing months: {missing}")
    else:
        raise TypeError("seasonal_multiplier must be a number, 12-value list, or month dict.")
    return np.array([values[int(month)] for month in timestamps.month], dtype=float)


def _calibrate_to_peak_and_load_factor(
    shape: np.ndarray, peak_demand_mw: float, load_factor: float
) -> np.ndarray:
    if peak_demand_mw <= 0.0:
        raise ValueError("peak_demand_mw must be positive.")
    if not 0.0 < load_factor <= 1.0:
        raise ValueError("load_factor must be between 0 and 1.")

    normalized = np.clip(shape / np.max(shape), 1.0e-6, 1.0)

    # Raising a positive normalized shape to a power preserves the peak and
    # lets us tune the mean load factor without adding an arbitrary baseload.
    low, high = 0.02, 12.0
    for _ in range(80):
        gamma = (low + high) / 2.0
        mean_factor = float(np.mean(normalized**gamma))
        if mean_factor > load_factor:
            low = gamma
        else:
            high = gamma

    calibrated = normalized ** ((low + high) / 2.0)
    calibrated *= peak_demand_mw
    return calibrated


def build_calibrated_load_archetype(
    timestamps: pd.DatetimeIndex,
    config: dict[str, Any] | None = None,
    seed: int = 42,
) -> pd.Series:
    """Build an editable island load profile with exact peak and load factor.

    Key calibration inputs are:
    - peak_demand_mw
    - load_factor
    - evening_peak_strength
    - seasonal_multiplier
    - tourism_load and commercial_load options
    """

    cfg = config or {}
    rng = np.random.default_rng(int(cfg.get("seed", seed)))

    peak_demand_mw = float(cfg.get("peak_demand_mw", 1.65))
    load_factor = float(cfg.get("load_factor", 0.72))
    evening_peak_strength = float(cfg.get("evening_peak_strength", 0.28))
    morning_peak_strength = float(cfg.get("morning_peak_strength", 0.10))
    commercial_fraction = float(cfg.get("commercial_load_fraction", 0.12))
    noise_fraction = float(cfg.get("random_noise_fraction", 0.025))

    hour = timestamps.hour.to_numpy()
    day_of_year = timestamps.dayofyear.to_numpy()
    weekday = timestamps.weekday.to_numpy()
    month = timestamps.month.to_numpy()

    base = np.full(len(timestamps), 1.0)
    morning_peak = morning_peak_strength * np.exp(-0.5 * ((hour - 7) / 2.5) ** 2)
    evening_peak = evening_peak_strength * np.exp(-0.5 * ((hour - 20) / 3.0) ** 2)
    daytime_activity = commercial_fraction * np.exp(-0.5 * ((hour - 13) / 4.0) ** 2)
    weekend_shift = np.where(weekday >= 5, -0.025, 0.0)

    tourism_options = cfg.get("tourism_load", {}) or {}
    tourism_multiplier = float(tourism_options.get("peak_month_multiplier", 1.0))
    tourism_months = {int(item) for item in tourism_options.get("peak_months", [])}
    tourism_shape = np.zeros(len(timestamps))
    if tourism_months and tourism_multiplier > 1.0:
        evening_leisure = np.exp(-0.5 * ((hour - 21) / 3.5) ** 2)
        weekend_leisure = np.where(weekday >= 5, 0.4, 0.0)
        in_tourism_month = np.array([int(item) in tourism_months for item in month])
        tourism_shape = in_tourism_month * (tourism_multiplier - 1.0) * (
            0.65 * evening_leisure + weekend_leisure
        )

    # A small tropical cooling signal keeps the archetype appropriate for a
    # Philippines off-grid case without hard-coding any measured load data.
    tropical_cooling = 0.06 * np.exp(-0.5 * ((day_of_year - 120) / 65.0) ** 2)
    seasonal = _monthly_multipliers(timestamps, cfg.get("seasonal_multiplier"))
    random_noise = rng.normal(0.0, noise_fraction, size=len(timestamps))

    shape = (
        base
        + morning_peak
        + evening_peak
        + daytime_activity
        + weekend_shift
        + tourism_shape
        + tropical_cooling
        + random_noise
    )
    shape = np.clip(shape * seasonal, 0.05, None)
    load_mw = _calibrate_to_peak_and_load_factor(shape, peak_demand_mw, load_factor)
    return pd.Series(load_mw.round(4), index=timestamps, name="load_mw")
