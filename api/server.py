from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api.battery_config import load_battery_config, save_battery_config

RESULTS_DIR = Path(__file__).resolve().parent.parent / "optimisation" / "results"
REALIZED_MTU_FILE = RESULTS_DIR / "realized_pnl_mtu.csv"
REALIZED_SUMMARY_FILE = RESULTS_DIR / "realized_pnl_summary.csv"

HOST = "127.0.0.1"
PORT = int(os.getenv("BATTERY_CONFIG_API_PORT", "8001"))


class ApiHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._send_json({}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self._path == "/api/battery-config":
            self._send_json(asdict(load_battery_config()))
            return

        if self._path == "/api/realized-pnl":
            self._send_json(self._load_realized_pnl())
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def _load_realized_pnl(self) -> dict[str, Any]:
        if not REALIZED_MTU_FILE.exists() or not REALIZED_SUMMARY_FILE.exists():
            return {
                "available": False,
                "message": "Realized PnL not yet evaluated. Run optimisation/realized_pnl.py after DAM clearing.",
                "summary": None,
                "mtu": [],
            }

        summary = _read_single_row_csv(REALIZED_SUMMARY_FILE)
        mtu_rows = _read_csv_rows(REALIZED_MTU_FILE)

        return {
            "available": True,
            "summary": summary,
            "mtu": mtu_rows,
        }

    def do_PUT(self) -> None:
        self._save_config()

    def do_POST(self) -> None:
        if self._path == "/api/realized-pnl/fetch":
            self._fetch_and_evaluate()
            return
        self._save_config()

    def _fetch_and_evaluate(self) -> None:
        from datetime import date as _date, datetime as _datetime

        try:
            payload = self._read_json_body() if int(self.headers.get("content-length", "0")) else {}
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        date_str = (payload or {}).get("date")
        try:
            target = (
                _datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else _date.today()
            )
        except ValueError:
            self._send_json({"error": "date must be YYYY-MM-DD"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            from optimisation.henex_dam import fetch_actual_prices
            from optimisation.realized_pnl import (
                evaluate as _evaluate,
                load_actual_prices as _load_actual,
                load_schedule as _load_schedule,
                MTU_OUT_PATH,
                SUMMARY_OUT_PATH,
                SCHEDULE_PATH_DEFAULT,
            )
            from optimisation.tier_final import load_battery_params

            _, source_url, csv_path = fetch_actual_prices(target)
            bp = load_battery_params()
            schedule = _load_schedule(SCHEDULE_PATH_DEFAULT)
            actual = _load_actual(csv_path, schedule)
            mtu_df, summary = _evaluate(schedule, actual, bp)

            import pandas as _pd
            mtu_df.to_csv(MTU_OUT_PATH, index=False)
            _pd.DataFrame([summary]).to_csv(SUMMARY_OUT_PATH, index=False)
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {"error": str(exc), "type": exc.__class__.__name__},
                status=HTTPStatus.BAD_GATEWAY,
            )
            return

        self._send_json({
            "ok": True,
            "delivery_day": target.isoformat(),
            "source_url": source_url,
            "csv_path": str(csv_path),
            "summary": self._load_realized_pnl().get("summary"),
        })

    def _save_config(self) -> None:
        if self._path != "/api/battery-config":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            config = save_battery_config(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(asdict(config))

    @property
    def _path(self) -> str:
        return urlparse(self.path).path

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length)
        return json.loads(raw_body.decode("utf-8") or "{}")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _coerce(value: str) -> Any:
    if value == "" or value.lower() == "nan":
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        return value


def _read_single_row_csv(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            return {k: _coerce(v) for k, v in row.items()}
    return {}


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [{k: _coerce(v) for k, v in row.items()} for row in reader]


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Battery config API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
