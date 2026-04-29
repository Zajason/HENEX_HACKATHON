"""Centralized path constants for the optimisation package.

All tier scripts import from here so outputs land in the right directories.
"""

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent

SYNTHETIC_DIR = _PKG_DIR / "synthetic"
RESULTS_DIR = _PKG_DIR / "results"
PLOTS_DIR = _PKG_DIR / "plots"

for _d in (SYNTHETIC_DIR, RESULTS_DIR, PLOTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def synthetic(name: str) -> Path:
    return SYNTHETIC_DIR / name


def result(name: str) -> Path:
    return RESULTS_DIR / name


def plot(name: str) -> Path:
    return PLOTS_DIR / name
