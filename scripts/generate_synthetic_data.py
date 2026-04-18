"""Generate one reproducible 8760-hour calibrated synthetic island dataset."""

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
)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_synthetic_island(
    year: int = 2025, seed: int = 42, config: dict | None = None
) -> pd.DataFrame:
    """Create hourly load and PV resource data for a non-leap analysis year."""

    cfg = config or {}
    timestamps = build_hourly_timestamps(year)
    load_config_data = cfg.get("load_archetype", {})
    weather_config = cfg.get("weather", {})

    load = build_calibrated_load_archetype(
        timestamps,
        config=load_config_data,
        seed=int(load_config_data.get("seed", seed)),
    )
    pv_resource = build_synthetic_pv_resource(
        timestamps,
        seed=int(weather_config.get("synthetic_seed", seed)),
        tropical=bool(weather_config.get("tropical_solar_resource", False)),
    )

    case_study = cfg.get("case_study", {})
    case_id = case_study.get("case_id", "synthetic_island")

    data = pd.DataFrame(
        {
            "timestamp": timestamps.astype(str),
            "load_mw": load.to_numpy(),
        }
    )
    data = data.merge(pv_resource, on="timestamp", how="left")
    data["case_id"] = case_id
    data["load_source"] = "calibrated_synthetic_archetype"
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "scenarios.json",
        help="Config file containing load_archetype and weather assumptions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "synthetic_island_8760.csv",
    )
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = load_config(config_path)
    year = int(config.get("analysis_year", args.year))

    data = build_synthetic_island(year=year, seed=args.seed, config=config)
    if len(data) != 8760:
        raise RuntimeError(f"Expected 8760 rows, got {len(data)}.")
    data.to_csv(output, index=False)
    print(f"Wrote {output} ({len(data)} rows)")


if __name__ == "__main__":
    main()
