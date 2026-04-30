from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

API_DIR = Path(__file__).resolve().parent
DATA_DIR = API_DIR / "data"
BATTERY_CONFIG_PATH = DATA_DIR / "battery_config.json"


@dataclass(frozen=True)
class BatteryUnit:
    id: str
    name: str
    quantity: int = 1
    capacity: float = 10.0
    power: float = 5.0
    socMin: float = 10.0
    socMax: float = 90.0
    socInitial: float = 15.0
    chargeEff: float = 92.0
    dischargeEff: float = 90.0
    degradationCost: float = 2.5


@dataclass(frozen=True)
class BatteryConfig:
    batteries: list[BatteryUnit]


DEFAULT_BATTERY_UNIT = BatteryUnit(id="battery-1", name="Battery 1")
DEFAULT_BATTERY_CONFIG = BatteryConfig(batteries=[DEFAULT_BATTERY_UNIT])


def _as_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return float(value)


def _as_percent(value: Any, field: str) -> float:
    percent = _as_number(value, field)
    if percent > 100:
        raise ValueError(f"{field} must be at most 100")
    return percent


def _validate_battery_unit(payload: dict[str, Any], index: int) -> BatteryUnit:
    merged = {**asdict(DEFAULT_BATTERY_UNIT), **payload}
    unit_id = merged.get("id") or f"battery-{index + 1}"
    name = merged.get("name") or f"Battery {index + 1}"
    if not isinstance(unit_id, str):
        raise ValueError(f"batteries[{index}].id must be a string")
    if not isinstance(name, str):
        raise ValueError(f"batteries[{index}].name must be a string")
    quantity = _as_number(merged["quantity"], f"batteries[{index}].quantity")
    if int(quantity) != quantity:
        raise ValueError(f"batteries[{index}].quantity must be a whole number")
    if quantity < 1:
        raise ValueError(f"batteries[{index}].quantity must be at least 1")
    soc_min = _as_percent(merged["socMin"], f"batteries[{index}].socMin")
    soc_max = _as_percent(merged["socMax"], f"batteries[{index}].socMax")
    soc_initial = _as_percent(merged["socInitial"], f"batteries[{index}].socInitial")
    if soc_min > soc_max:
        raise ValueError(f"batteries[{index}].socMin must be less than or equal to socMax")
    if not soc_min <= soc_initial <= soc_max:
        raise ValueError(f"batteries[{index}].socInitial must be between socMin and socMax")

    return BatteryUnit(
        id=unit_id,
        name=name,
        quantity=int(quantity),
        capacity=_as_number(merged["capacity"], f"batteries[{index}].capacity"),
        power=_as_number(merged["power"], f"batteries[{index}].power"),
        socMin=soc_min,
        socMax=soc_max,
        socInitial=soc_initial,
        chargeEff=_as_number(merged["chargeEff"], f"batteries[{index}].chargeEff"),
        dischargeEff=_as_number(merged["dischargeEff"], f"batteries[{index}].dischargeEff"),
        degradationCost=_as_number(merged["degradationCost"], f"batteries[{index}].degradationCost"),
    )


def _migrate_legacy_config(payload: dict[str, Any]) -> dict[str, Any]:
    count = int(_as_number(payload.get("batteries", 1), "batteries"))
    if count < 1:
        count = 1

    batteries = []
    batteries.append(
        {
            "id": "battery-block-1",
            "name": "Battery block 1",
            "quantity": count,
            "capacity": payload.get("capacity", DEFAULT_BATTERY_UNIT.capacity),
            "power": payload.get("power", DEFAULT_BATTERY_UNIT.power),
            "socMin": payload.get("socMin", DEFAULT_BATTERY_UNIT.socMin),
            "socMax": payload.get("socMax", DEFAULT_BATTERY_UNIT.socMax),
            "socInitial": payload.get("socInitial", DEFAULT_BATTERY_UNIT.socInitial),
            "chargeEff": payload.get("chargeEff", DEFAULT_BATTERY_UNIT.chargeEff),
            "dischargeEff": payload.get("dischargeEff", DEFAULT_BATTERY_UNIT.dischargeEff),
            "degradationCost": payload.get("degradationCost", DEFAULT_BATTERY_UNIT.degradationCost),
        }
    )
    return {"batteries": batteries}


def validate_battery_config(payload: dict[str, Any]) -> BatteryConfig:
    if isinstance(payload.get("batteries"), (int, float)):
        payload = _migrate_legacy_config(payload)

    batteries = payload.get("batteries", asdict(DEFAULT_BATTERY_CONFIG)["batteries"])
    if not isinstance(batteries, list):
        raise ValueError("batteries must be a list")
    if len(batteries) == 0:
        raise ValueError("at least one battery is required")

    validated = []
    for index, battery in enumerate(batteries):
        if not isinstance(battery, dict):
            raise ValueError(f"batteries[{index}] must be an object")
        validated.append(_validate_battery_unit(battery, index))

    return BatteryConfig(batteries=validated)


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
