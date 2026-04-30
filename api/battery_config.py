from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Mode = Literal["conservative", "aggressive"]

API_DIR = Path(__file__).resolve().parent
DATA_DIR = API_DIR / "data"
BATTERY_CONFIG_PATH = DATA_DIR / "battery_config.json"


@dataclass(frozen=True)
class BatteryConfig:
    batteries: int = 4
    capacity: float = 10.0
    power: float = 5.0
    chargeEff: float = 92.0
    dischargeEff: float = 90.0
    degradationCost: float = 2.5
    mode: Mode = "aggressive"


DEFAULT_BATTERY_CONFIG = BatteryConfig()


def _as_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return float(value)


def validate_battery_config(payload: dict[str, Any]) -> BatteryConfig:
    merged = {**asdict(DEFAULT_BATTERY_CONFIG), **payload}
    mode = merged["mode"]
    if mode not in ("conservative", "aggressive"):
        raise ValueError("mode must be 'conservative' or 'aggressive'")

    batteries = _as_number(merged["batteries"], "batteries")
    if int(batteries) != batteries:
        raise ValueError("batteries must be a whole number")

    return BatteryConfig(
        batteries=int(batteries),
        capacity=_as_number(merged["capacity"], "capacity"),
        power=_as_number(merged["power"], "power"),
        chargeEff=_as_number(merged["chargeEff"], "chargeEff"),
        dischargeEff=_as_number(merged["dischargeEff"], "dischargeEff"),
        degradationCost=_as_number(merged["degradationCost"], "degradationCost"),
        mode=mode,
    )


def load_battery_config(path: Path = BATTERY_CONFIG_PATH) -> BatteryConfig:
    if not path.exists():
        return DEFAULT_BATTERY_CONFIG

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("battery config file must contain a JSON object")
    return validate_battery_config(payload)


def save_battery_config(payload: dict[str, Any], path: Path = BATTERY_CONFIG_PATH) -> BatteryConfig:
    config = validate_battery_config(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2)
        f.write("\n")
    return config


def get_battery_config_dict() -> dict[str, Any]:
    """Import this from optimization scripts to read the latest frontend config."""
    return asdict(load_battery_config())
