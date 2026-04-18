"""Weather and PV resource preparation helpers.

External support is intentionally CSV-first so the project remains easy to run
on Windows with the existing lightweight dependencies. NASA POWER hourly CSVs
and ERA5 CSV exports are both normalized into the baseline model columns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


NASA_GHI_COLUMNS = [
    "ALLSKY_SFC_SW_DWN",
    "CLRSKY_SFC_SW_DWN",
    "ghi_w_per_m2",
    "GHI",
]
ERA5_GHI_COLUMNS = [
    "ssrd",
    "surface_solar_radiation_downwards",
    "ghi_w_per_m2",
    "GHI",
]
TEMPERATURE_COLUMNS = ["T2M", "t2m", "temperature_c", "temperature_2m"]


def build_synthetic_pv_resource(
    timestamps: pd.DatetimeIndex, seed: int = 42, tropical: bool = False
) -> pd.DataFrame:
    """Create a reproducible synthetic PV resource for an 8760-hour year."""

    rng = np.random.default_rng(seed)
    hour = timestamps.hour.to_numpy()
    day_of_year = timestamps.dayofyear.to_numpy()

    daylight_shape = np.maximum(0.0, np.sin(np.pi * (hour - 6) / 12.0))
    if tropical:
        seasonal_solar = 0.88 + 0.12 * np.cos(2.0 * np.pi * (day_of_year - 95) / 365.0)
        temperature_base = 27.0
        seasonal_temperature = 2.5 * np.sin(2.0 * np.pi * (day_of_year - 100) / 365.0)
    else:
        seasonal_solar = 0.78 + 0.22 * np.cos(2.0 * np.pi * (day_of_year - 172) / 365.0)
        temperature_base = 18.0
        seasonal_temperature = 8.0 * np.sin(2.0 * np.pi * (day_of_year - 172) / 365.0)

    daily_cloud = rng.beta(5.0, 2.0, size=365)
    cloud = np.repeat(daily_cloud, 24)
    pv_capacity_factor = np.clip(0.88 * daylight_shape * seasonal_solar * cloud, 0.0, 0.92)
    ghi_w_per_m2 = np.clip(pv_capacity_factor / 0.20 * 1000.0, 0.0, 1000.0)
    temperature_c = (
        temperature_base
        + seasonal_temperature
        + 3.0 * np.sin(2.0 * np.pi * (hour - 14) / 24.0)
        + rng.normal(0.0, 1.5, size=len(timestamps))
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps.astype(str),
            "pv_capacity_factor": pv_capacity_factor.round(5),
            "ghi_w_per_m2": ghi_w_per_m2.round(1),
            "temperature_c": temperature_c.round(2),
            "pv_source": "synthetic",
        }
    )


def pv_capacity_factor_from_weather(
    ghi_w_per_m2: pd.Series,
    temperature_c: pd.Series | None = None,
    derate: float = 0.82,
    temperature_coefficient_per_c: float = -0.004,
) -> pd.Series:
    """Convert hourly GHI and temperature to a simple PV capacity factor."""

    ghi = pd.to_numeric(ghi_w_per_m2, errors="coerce").fillna(0.0).clip(lower=0.0)
    if temperature_c is None:
        temp = pd.Series(25.0, index=ghi.index)
    else:
        temp = pd.to_numeric(temperature_c, errors="coerce").fillna(25.0)
        if temp.median() > 150.0:
            temp = temp - 273.15

    cell_temperature_c = temp + 0.0256 * ghi
    temperature_factor = 1.0 + temperature_coefficient_per_c * (cell_temperature_c - 25.0)
    cf = (ghi / 1000.0) * derate * temperature_factor
    return cf.clip(lower=0.0, upper=1.0).round(5)


def _read_csv_with_detected_header(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header_index = 0
    for index, line in enumerate(lines):
        upper = line.upper()
        if (
            ("YEAR" in upper and "MO" in upper and "DY" in upper)
            or "TIMESTAMP" in upper
            or "VALID_TIME" in upper
            or upper.startswith("TIME,")
        ):
            header_index = index
            break
    return pd.read_csv(path, skiprows=header_index)


def _find_column(data: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().lower(): column for column in data.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return str(lookup[candidate.lower()])
    return None


def _timestamps_from_weather(data: pd.DataFrame) -> pd.Series:
    columns = {str(column).strip().upper(): column for column in data.columns}
    if {"YEAR", "MO", "DY", "HR"}.issubset(columns):
        base = pd.to_datetime(
            {
                "year": data[columns["YEAR"]].astype(int),
                "month": data[columns["MO"]].astype(int),
                "day": data[columns["DY"]].astype(int),
            }
        )
        return base + pd.to_timedelta(data[columns["HR"]].astype(int), unit="h")

    for candidate in ["timestamp", "time", "valid_time", "datetime", "date"]:
        column = _find_column(data, [candidate])
        if column is not None:
            return pd.to_datetime(data[column])
    raise ValueError("Weather file must include timestamp/time or YEAR,MO,DY,HR columns.")


def _normalize_irradiance(values: pd.Series, source_format: str, unit: str = "auto") -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if unit == "w_per_m2":
        return numeric.clip(lower=0.0)
    if unit == "j_per_m2":
        return (numeric / 3600.0).clip(lower=0.0)
    if unit == "kwh_per_m2":
        return (numeric * 1000.0).clip(lower=0.0)

    max_value = float(numeric.max())
    if source_format == "era5" or max_value > 10000.0:
        return (numeric / 3600.0).clip(lower=0.0)
    if max_value <= 2.0:
        return (numeric * 1000.0).clip(lower=0.0)
    return numeric.clip(lower=0.0)


def load_external_weather_resource(
    path: Path,
    source_format: str = "auto",
    expected_year: int | None = None,
    irradiance_unit: str = "auto",
    pv_settings: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Load NASA POWER or ERA5 hourly CSV data and compute PV capacity factor."""

    path = Path(path)
    if path.suffix.lower() in {".nc", ".grib", ".grb"}:
        raise ValueError(
            "NetCDF/GRIB weather files are not read directly to keep dependencies light. "
            "Export ERA5 to hourly CSV with a time column and ssrd or ghi_w_per_m2."
        )

    data = _read_csv_with_detected_header(path)
    source = source_format.lower()
    if source == "auto":
        upper_columns = {str(column).strip().upper() for column in data.columns}
        lower_columns = {str(column).strip().lower() for column in data.columns}
        if "ALLSKY_SFC_SW_DWN" in upper_columns:
            source = "nasa-power"
        elif "ssrd" in lower_columns or "surface_solar_radiation_downwards" in lower_columns:
            source = "era5"
        else:
            source = "csv"

    timestamps = _timestamps_from_weather(data)
    if expected_year is not None:
        data = data.loc[timestamps.dt.year == expected_year].copy()
        timestamps = timestamps.loc[data.index]

    ghi_column = _find_column(data, NASA_GHI_COLUMNS + ERA5_GHI_COLUMNS)
    if ghi_column is None and _find_column(data, ["pv_capacity_factor"]) is None:
        raise ValueError(
            "Weather file must include irradiance (for example ALLSKY_SFC_SW_DWN, ssrd, "
            "or ghi_w_per_m2) or pv_capacity_factor."
        )

    temp_column = _find_column(data, TEMPERATURE_COLUMNS)
    if ghi_column is not None:
        ghi = _normalize_irradiance(data[ghi_column], source_format=source, unit=irradiance_unit)
    else:
        ghi = pd.Series(0.0, index=data.index)

    if _find_column(data, ["pv_capacity_factor"]) is not None:
        cf_column = _find_column(data, ["pv_capacity_factor"])
        pv_capacity_factor = pd.to_numeric(data[cf_column], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    else:
        settings = pv_settings or {}
        pv_capacity_factor = pv_capacity_factor_from_weather(
            ghi,
            data[temp_column] if temp_column is not None else None,
            derate=float(settings.get("pv_derate", 0.82)),
            temperature_coefficient_per_c=float(settings.get("temperature_coefficient_per_c", -0.004)),
        )

    temperature = (
        pd.to_numeric(data[temp_column], errors="coerce") if temp_column is not None else pd.Series(np.nan, index=data.index)
    )
    if temperature.notna().any() and temperature.median() > 150.0:
        temperature = temperature - 273.15

    resource = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps).dt.strftime("%Y-%m-%d %H:%M:%S"),
            "pv_capacity_factor": pv_capacity_factor.round(5).to_numpy(),
            "ghi_w_per_m2": ghi.round(1).to_numpy(),
            "temperature_c": temperature.round(2).to_numpy(),
            "pv_source": source,
        }
    )
    resource = resource.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if len(resource) != 8760:
        raise ValueError(f"Expected 8760 hourly weather rows, found {len(resource)}.")
    return resource
