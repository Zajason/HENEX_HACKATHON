"""Daily 12:00 optimisation runner for tier_final2.

A background thread that wakes up once per day at 12:00 local time and runs
`python -m optimisation.tier_final2` as a subprocess. Output CSV is written
to `optimisation/results/tier_final2_schedule.csv`, which is what the
realized-PnL evaluator reads.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "optimisation" / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "tier_final2_runs.log"

DAILY_RUN_AT = time(hour=12, minute=0)

_state_lock = threading.Lock()
_state: dict = {
    "last_run_started": None,
    "last_run_finished": None,
    "last_exit_code": None,
    "last_error": None,
    "next_run_at": None,
    "running": False,
}


def get_state() -> dict:
    with _state_lock:
        s = dict(_state)
    s["last_run_started"] = s["last_run_started"].isoformat() if s["last_run_started"] else None
    s["last_run_finished"] = s["last_run_finished"].isoformat() if s["last_run_finished"] else None
    s["next_run_at"] = s["next_run_at"].isoformat() if s["next_run_at"] else None
    return s


def _seconds_until_next_noon(now: Optional[datetime] = None) -> tuple[float, datetime]:
    now = now or datetime.now()
    today_noon = datetime.combine(now.date(), DAILY_RUN_AT)
    target = today_noon if now < today_noon else today_noon + timedelta(days=1)
    return (target - now).total_seconds(), target


def run_optimiser_blocking() -> int:
    """Run tier_final2 as a subprocess. Returns exit code. Updates _state."""
    cmd = [sys.executable, "-m", "optimisation.tier_final2"]
    started = datetime.now()
    with _state_lock:
        _state["running"] = True
        _state["last_run_started"] = started
        _state["last_error"] = None

    with open(LOG_FILE, "ab") as log:
        log.write(f"\n===== {started.isoformat()} =====\n".encode())
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )

    finished = datetime.now()
    with _state_lock:
        _state["running"] = False
        _state["last_run_finished"] = finished
        _state["last_exit_code"] = proc.returncode
        if proc.returncode != 0:
            _state["last_error"] = f"exit code {proc.returncode} — see {LOG_FILE}"
    return proc.returncode


def trigger_async() -> None:
    """Manual one-shot trigger (returns immediately)."""
    threading.Thread(target=run_optimiser_blocking, daemon=True).start()


def _scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        secs, target = _seconds_until_next_noon()
        with _state_lock:
            _state["next_run_at"] = target
        if stop_event.wait(timeout=secs):
            return
        try:
            run_optimiser_blocking()
        except Exception as exc:  # noqa: BLE001
            with _state_lock:
                _state["running"] = False
                _state["last_error"] = repr(exc)


def start_scheduler() -> threading.Event:
    """Start the daily-noon scheduler thread. Returns a stop event."""
    stop_event = threading.Event()
    t = threading.Thread(target=_scheduler_loop, args=(stop_event,), daemon=True)
    t.start()
    _, target = _seconds_until_next_noon()
    with _state_lock:
        _state["next_run_at"] = target
    print(f"Scheduler armed: next tier_final2 run at {target.isoformat()}")
    return stop_event
