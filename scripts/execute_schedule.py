"""Execute a battery schedule by posting control commands at scheduled times.

Example:
    python3 -m scripts.execute_schedule \
        optimisation/results/tier1_cvar_schedule.csv \
        --dry-run

The input CSV should look like the optimisation tier outputs:
`timestamp, charge_mw, discharge_mw, ...` or include an action column such as
`mpc_action` with values `charge`, `discharge`, or `idle`.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ACTION_IDLE = "idle"
ACTION_CHARGE = "charge"
ACTION_DISCHARGE = "discharge"

COMMAND_CHARGE = "charge"
COMMAND_DISCHARGE = "discharge"
COMMAND_STOP_CHARGING = "stop_charging"
COMMAND_STOP_DISCHARGING = "stop_discharging"

BATTERY_CONTROL_ENDPOINT = "http://127.0.0.1:9000/battery/control"


@dataclass(frozen=True)
class ScheduleRow:
    timestamp: datetime
    action: str
    charge_mw: float
    discharge_mw: float
    raw: dict[str, str]


@dataclass(frozen=True)
class ScheduledCommand:
    timestamp: datetime
    command: str
    action: str
    charge_mw: float
    discharge_mw: float


def parse_timestamp(value: str) -> datetime:
    cleaned = value.strip().replace("T", " ")
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def parse_float(value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def infer_action(row: dict[str, str]) -> str:
    explicit = row.get("mpc_action") or row.get("action") or row.get("decision") or row.get("mode")
    if explicit:
        action = explicit.strip().lower()
        if action in {ACTION_CHARGE, ACTION_DISCHARGE, ACTION_IDLE}:
            return action

    charge_mw = parse_float(
        row.get("charge_mw")
        or row.get("mpc_charge_mw")
        or row.get("dam_charge_mw")
    )
    discharge_mw = parse_float(
        row.get("discharge_mw")
        or row.get("mpc_discharge_mw")
        or row.get("dam_discharge_mw")
    )
    if charge_mw > 0 and charge_mw >= discharge_mw:
        return ACTION_CHARGE
    if discharge_mw > 0:
        return ACTION_DISCHARGE
    return ACTION_IDLE


def load_schedule(path: str) -> list[ScheduleRow]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "timestamp" not in reader.fieldnames:
            raise ValueError("Schedule CSV must contain a timestamp column.")

        rows = []
        for raw in reader:
            rows.append(
                ScheduleRow(
                    timestamp=parse_timestamp(raw["timestamp"]),
                    action=infer_action(raw),
                    charge_mw=parse_float(raw.get("charge_mw") or raw.get("mpc_charge_mw") or raw.get("dam_charge_mw")),
                    discharge_mw=parse_float(
                        raw.get("discharge_mw") or raw.get("mpc_discharge_mw") or raw.get("dam_discharge_mw")
                    ),
                    raw=raw,
                )
            )

    return sorted(rows, key=lambda row: row.timestamp)


def build_commands(rows: Iterable[ScheduleRow]) -> list[ScheduledCommand]:
    rows = list(rows)
    commands = []
    previous_action = ACTION_IDLE
    default_interval = timedelta(minutes=15)

    for row in rows:
        if row.action == previous_action:
            continue

        if previous_action == ACTION_CHARGE:
            commands.append(
                ScheduledCommand(
                    timestamp=row.timestamp,
                    command=COMMAND_STOP_CHARGING,
                    action=row.action,
                    charge_mw=0.0,
                    discharge_mw=row.discharge_mw,
                )
            )
        elif previous_action == ACTION_DISCHARGE:
            commands.append(
                ScheduledCommand(
                    timestamp=row.timestamp,
                    command=COMMAND_STOP_DISCHARGING,
                    action=row.action,
                    charge_mw=row.charge_mw,
                    discharge_mw=0.0,
                )
            )

        if row.action == ACTION_CHARGE:
            commands.append(
                ScheduledCommand(
                    timestamp=row.timestamp,
                    command=COMMAND_CHARGE,
                    action=row.action,
                    charge_mw=row.charge_mw,
                    discharge_mw=0.0,
                )
            )
        elif row.action == ACTION_DISCHARGE:
            commands.append(
                ScheduledCommand(
                    timestamp=row.timestamp,
                    command=COMMAND_DISCHARGE,
                    action=row.action,
                    charge_mw=0.0,
                    discharge_mw=row.discharge_mw,
                )
            )

        previous_action = row.action

    if rows and previous_action in {ACTION_CHARGE, ACTION_DISCHARGE}:
        interval = default_interval
        if len(rows) > 1:
            inferred_interval = rows[-1].timestamp - rows[-2].timestamp
            if inferred_interval.total_seconds() > 0:
                interval = inferred_interval

        commands.append(
            ScheduledCommand(
                timestamp=rows[-1].timestamp + interval,
                command=COMMAND_STOP_CHARGING if previous_action == ACTION_CHARGE else COMMAND_STOP_DISCHARGING,
                action=ACTION_IDLE,
                charge_mw=0.0,
                discharge_mw=0.0,
            )
        )

    return commands


def post_command(endpoint: str, command: ScheduledCommand, timeout: float) -> None:
    payload = {
        "timestamp": command.timestamp.isoformat(sep=" "),
        "command": command.command,
        "target_action": command.action,
        "charge_mw": command.charge_mw,
        "discharge_mw": command.discharge_mw,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        response.read()


def wait_until(timestamp: datetime, time_scale: float) -> None:
    delay = (timestamp - datetime.now(timestamp.tzinfo)).total_seconds()
    if delay > 0:
        time.sleep(delay / time_scale)


def execute_commands(
    commands: Iterable[ScheduledCommand],
    endpoint: str,
    dry_run: bool,
    skip_past: bool,
    timeout: float,
    time_scale: float,
) -> None:
    if time_scale <= 0:
        raise ValueError("--time-scale must be greater than zero.")

    for command in commands:
        if skip_past and command.timestamp < datetime.now(command.timestamp.tzinfo):
            print(f"[skip] {command.timestamp} {command.command}")
            continue

        wait_until(command.timestamp, time_scale)
        print(
            f"[send] {command.timestamp} {command.command} "
            f"charge_mw={command.charge_mw:g} discharge_mw={command.discharge_mw:g}"
        )
        if dry_run:
            continue

        try:
            post_command(endpoint, command, timeout)
        except HTTPError as exc:
            raise RuntimeError(f"Endpoint returned HTTP {exc.code} for {command.command}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach endpoint for {command.command}: {exc.reason}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Post battery control commands from an optimisation schedule CSV.")
    parser.add_argument("schedule_csv", help="Path to a tier schedule CSV.")
    parser.add_argument(
        "--endpoint",
        default=BATTERY_CONTROL_ENDPOINT,
        help=f"Battery control API endpoint that accepts POST JSON. Defaults to {BATTERY_CONTROL_ENDPOINT}.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without posting them.")
    parser.add_argument("--skip-past", action="store_true", help="Skip commands whose timestamps are already in the past.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--time-scale",
        type=float,
        default=1.0,
        help="Speed up waiting for demos. 60 means one real second equals one scheduled minute.",
    )
    args = parser.parse_args()

    rows = load_schedule(args.schedule_csv)
    commands = build_commands(rows)
    if not commands:
        print("No action changes found in schedule.")
        return

    execute_commands(
        commands=commands,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
        skip_past=args.skip_past,
        timeout=args.timeout,
        time_scale=args.time_scale,
    )


if __name__ == "__main__":
    main()
