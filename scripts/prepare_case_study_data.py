"""Prepare an ASEAN case-study dataset from calibrated load and weather input."""

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
    build_calibrated_load_archetype,
    build_hourly_timestamps,
    build_synthetic_pv_resource,
    load_external_weather_resource,
)


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-config",
        type=Path,
        default=ROOT / "configs" / "cases" / "philippines_offgrid.json",
        help="Case-study configuration with metadata and load archetype settings.",
    )
    parser.add_argument(
        "--weather-file",
        type=Path,
        default=None,
        help="Optional NASA POWER or ERA5 hourly CSV. If omitted, synthetic PV is used.",
    )
    parser.add_argument(
        "--weather-format",
        default="auto",
        choices=["auto", "nasa-power", "era5", "csv"],
        help="External weather parser. auto detects NASA POWER or ERA5 CSV columns.",
    )
    parser.add_argument(
        "--irradiance-unit",
        default="auto",
        choices=["auto", "w_per_m2", "j_per_m2", "kwh_per_m2"],
        help="Unit for the irradiance column when auto-detection is not enough.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "philippines_offgrid_8760.csv",
    )
    args = parser.parse_args()

    case_config_path = (
        args.case_config if args.case_config.is_absolute() else ROOT / args.case_config
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(case_config_path)
    year = int(config.get("analysis_year", 2025))
    timestamps = build_hourly_timestamps(year)

    load_config_data = config.get("load_archetype", {})
    load = build_calibrated_load_archetype(
        timestamps,
        config=load_config_data,
        seed=int(load_config_data.get("seed", 42)),
    )

    weather_file = args.weather_file
    if weather_file is not None:
        weather_path = weather_file if weather_file.is_absolute() else ROOT / weather_file
        pv_resource = load_external_weather_resource(
            weather_path,
            source_format=args.weather_format,
            expected_year=year,
            irradiance_unit=args.irradiance_unit,
            pv_settings=config.get("weather", {}),
        )
    else:
        weather = config.get("weather", {})
        pv_resource = build_synthetic_pv_resource(
            timestamps,
            seed=int(weather.get("synthetic_seed", 42)),
            tropical=bool(weather.get("tropical_solar_resource", True)),
        )

    case_study = config.get("case_study", {})
    data = pd.DataFrame(
        {
            "timestamp": timestamps.astype(str),
            "load_mw": load.to_numpy(),
        }
    )
    data = data.merge(pv_resource, on="timestamp", how="left")
    data["case_id"] = case_study.get("case_id", "philippines_offgrid")
    data["country"] = case_study.get("country", "Philippines")
    data["region"] = case_study.get("region", "ASEAN")
    data["load_source"] = "calibrated_synthetic_archetype"
    data["pv_source"] = data["pv_source"].fillna("external_weather")

    if data[["load_mw", "pv_capacity_factor"]].isna().any().any():
        raise RuntimeError("Prepared dataset contains missing load or PV capacity factor values.")
    if len(data) != 8760:
        raise RuntimeError(f"Expected 8760 rows, got {len(data)}.")

    data.to_csv(output, index=False)
    print(f"Wrote {output} ({len(data)} rows)")


if __name__ == "__main__":
    main()
