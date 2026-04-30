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

        if self._path == "/api/optimise/status":
            from api.scheduler import get_state
            self._send_json(get_state())
            return

        if self._path == "/api/dam/available-dates":
            try:
                from optimisation.henex_dam import list_available_dates
                dates = list_available_dates()
                self._send_json({"dates": dates})
            except Exception as exc:  # noqa: BLE001
                self._send_json(
                    {"error": str(exc), "type": exc.__class__.__name__, "dates": []},
                    status=HTTPStatus.BAD_GATEWAY,
                )
            return

        if self._path == "/api/backtest/summary":
            self._handle_backtest_summary()
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def _handle_backtest_summary(self) -> None:
        from urllib.parse import parse_qs
        params = parse_qs(urlparse(self.path).query)

        def _get(key: str, default: str) -> str:
            v = params.get(key, [default])
            return v[0] if v else default

        try:
            tier = int(_get("tier", "1"))
            lambda_str = _get("lambda", "")
            lambda_val = float(lambda_str) if lambda_str else None
            capex_per_mwh = float(_get("capex_per_mwh", "220000"))
            energy_mwh = float(_get("energy_mwh", "300"))
            rf_pct = float(_get("rf_pct", "3"))
        except ValueError as exc:
            self._send_json({"error": f"bad query: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        path = _resolve_summary_path(tier, lambda_val)
        if not path or not path.exists():
            self._send_json(
                {
                    "error": "summary not found for tier+lambda combo",
                    "tier": tier,
                    "lambda": lambda_val,
                    "tried_path": str(path) if path else None,
                },
                status=HTTPStatus.NOT_FOUND,
            )
            return

        row = _read_single_row_csv(path)
        try:
            profit = float(row["total_realized_profit_eur"])
            days = int(row["days"])
            throughput = float(row["total_throughput_mwh"])
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json(
                {"error": f"summary missing required fields: {exc}", "path": str(path)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        capex_eur = capex_per_mwh * energy_mwh
        annualized_profit = profit * 365.0 / days if days else 0.0
        return_pct = (annualized_profit / capex_eur * 100.0) if capex_eur > 0 else None
        excess_pct = (return_pct - rf_pct) if return_pct is not None else None

        cycles_per_day = float(row.get("mean_equivalent_cycles_per_day") or 0.0)
        life_years_6000 = (6000.0 / (cycles_per_day * 365.0)) if cycles_per_day > 0 else None
        life_years_8000 = (8000.0 / (cycles_per_day * 365.0)) if cycles_per_day > 0 else None

        result = {
            "tier": tier,
            "lambda": lambda_val,
            "source_path": str(path),
            "days": days,
            "start_date": row.get("start_date"),
            "end_date": row.get("end_date"),
            # raw model
            "profit_eur": profit,
            "annualized_profit_eur": annualized_profit,
            "throughput_mwh": throughput,
            "throughput_gwh": throughput / 1000.0,
            "cycles_per_day": cycles_per_day,
            "win_rate": row.get("win_rate"),
            "loss_rate": row.get("loss_rate"),
            "worst_day_eur": row.get("worst_day_profit_eur"),
            "best_day_eur": row.get("best_day_profit_eur"),
            "cvar5_eur": row.get("cvar5_daily_profit_eur"),
            "max_drawdown_eur": row.get("max_drawdown_eur"),
            "pnl_sharpe_annualized": row.get("annualized_pnl_sharpe") or row.get("annualized_sharpe"),
            "pnl_sortino_annualized": row.get("annualized_pnl_sortino") or row.get("annualized_sortino"),
            # CAPEX-dependent (recomputed)
            "capex_eur": capex_eur,
            "capex_per_mwh": capex_per_mwh,
            "energy_mwh": energy_mwh,
            "risk_free_rate_pct": rf_pct,
            "annualized_return_pct": return_pct,
            "annualized_excess_return_pct": excess_pct,
            # life
            "life_years_6000c": life_years_6000,
            "life_years_8000c": life_years_8000,
            # forecast quality
            "forecast_vs_realized_eur": row.get("forecast_vs_realized_profit_eur"),
            "expected_p50_profit_eur": row.get("total_expected_p50_profit_eur"),
        }
        self._send_json(result)

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
        if self._path == "/api/realized-pnl/upload":
            self._upload_and_evaluate()
            return
        if self._path == "/api/optimise/run":
            from datetime import date as _date, datetime as _datetime
            from api.scheduler import get_state, trigger_async

            if get_state()["running"]:
                self._send_json({"error": "Optimisation already running"}, status=HTTPStatus.CONFLICT)
                return

            try:
                payload = self._read_json_body() if int(self.headers.get("content-length", "0")) else {}
            except json.JSONDecodeError as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return

            target_date_str = (payload or {}).get("date")
            if target_date_str:
                try:
                    target_date_obj = _datetime.strptime(target_date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "date must be YYYY-MM-DD"}, status=HTTPStatus.BAD_REQUEST)
                    return
                min_date = _date(2025, 1, 1)
                max_date = _date.today()
                if target_date_obj < min_date or target_date_obj > max_date:
                    self._send_json(
                        {
                            "error": (
                                f"date out of range; must be between {min_date} and {max_date}"
                            ),
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            trigger_async(target_date_str)
            self._send_json({"ok": True, "started": True, "target_date": target_date_str, "state": get_state()})
            return
        self._save_config()

    def _fetch_and_evaluate(self) -> None:
        from datetime import datetime as _datetime

        try:
            payload = self._read_json_body() if int(self.headers.get("content-length", "0")) else {}
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        date_str = (payload or {}).get("date")

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

            schedule = _load_schedule(SCHEDULE_PATH_DEFAULT)
            schedule_day = schedule["timestamp"].iloc[0].date()

            if date_str:
                try:
                    requested = _datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "date must be YYYY-MM-DD"}, status=HTTPStatus.BAD_REQUEST)
                    return
                if requested != schedule_day:
                    self._send_json(
                        {
                            "error": (
                                f"Date mismatch: schedule covers delivery day {schedule_day}, "
                                f"but {requested} was requested. Re-run the optimiser for "
                                f"{requested} or fetch HEnEx prices for {schedule_day}."
                            ),
                            "schedule_day": schedule_day.isoformat(),
                            "requested_day": requested.isoformat(),
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                target = requested
            else:
                target = schedule_day

            _, source_url, csv_path = fetch_actual_prices(target)
            bp = load_battery_params()
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


def _resolve_summary_path(tier: int, lambda_val: float | None) -> Path | None:
    """Map (tier, lambda) to the precomputed summary CSV.
    Tier 0 has lambda sweeps under sweep_lambda_<x.xx>; Tier 3 under tier3_sweep_<x.xx>.
    Tier 1 / Tier 2 only have a default run today.
    """
    if tier == 0:
        if lambda_val is None or abs(lambda_val - 0.10) < 1e-9:
            return RESULTS_DIR / "2025_forecast_optimizer_summary.csv"
        # Try sweep_lambda_<X.XX> directory; lambdas saved as 0.00..0.35 in 2-digit form.
        candidates = [
            RESULTS_DIR / f"sweep_lambda_{lambda_val:.2f}" / "2025_forecast_optimizer_summary.csv",
            RESULTS_DIR / f"sweep_lambda_{lambda_val:.1f}" / "2025_forecast_optimizer_summary.csv",
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]
    if tier == 1:
        if lambda_val is None:
            return RESULTS_DIR / "2025_tier1_optimizer_summary.csv"
        sweep = RESULTS_DIR / f"tier1_sweep_{lambda_val:.2f}" / "2025_tier1_optimizer_summary.csv"
        if sweep.exists():
            return sweep
        return RESULTS_DIR / "2025_tier1_optimizer_summary.csv"
    if tier == 2:
        return RESULTS_DIR / "2025_tier2_optimizer_summary.csv"
    if tier == 3:
        if lambda_val is None or abs(lambda_val - 0.50) < 1e-9:
            return RESULTS_DIR / "2025_tier3_optimizer_summary.csv"
        candidates = [
            RESULTS_DIR / f"tier3_sweep_{lambda_val:.2f}" / "2025_tier3_optimizer_summary.csv",
        ]
        return candidates[0]
    return None


def main() -> None:
    from api.scheduler import start_scheduler
    start_scheduler()
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Battery config API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
