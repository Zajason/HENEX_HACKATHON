# AGENTS.md

Entry point for any coding agent (Claude Code, Cursor, etc.) working in this repo.

## What this project is

A hackathon submission for **Battery Optimization in the Greek Electricity Market** (HEnEx). The deliverable is a robust day-ahead battery scheduling framework that decides charge / discharge / idle for every 15-minute delivery period, maximizing economic value subject to physical constraints, **under intentional data scarcity** (Greece's first standalone batteries only entered DAM test mode in April 2026, so there is no rich battery telemetry history).

The framing — important — is **not** "predict tomorrow's prices." It is **"forecast the distribution of clearing prices, then run a degradation-aware stochastic optimizer over scenarios."** Battery as long price dispersion; losses, degradation, idle hold are the carry. See [STRATEGY.md](STRATEGY.md) and [GLOSSARY.md](GLOSSARY.md).

## Read order for a new agent

1. [STRATEGY.md](STRATEGY.md) — full strategic thesis (canonical; do not duplicate elsewhere)
2. [MEMORY.md](MEMORY.md) — current project state, decisions log, what's done
3. [PLAN.md](PLAN.md) — tiered execution roadmap (Tier 0 → 3)
4. [ARCHITECTURE.md](ARCHITECTURE.md) — module layout
5. Layer-specific spec for the layer being touched: [DATA.md](DATA.md), [FORECAST.md](FORECAST.md), [OPTIMIZER.md](OPTIMIZER.md)
6. [GLOSSARY.md](GLOSSARY.md) — vocabulary bridge if Greeks/options terms appear

## Commands

```bash
# install
pip install -r requirements.txt

# pull + align one delivery day
python data_pipeline.py
```

No test suite or formatter is wired up yet. Don't add one unless the user asks — premature scaffolding is one of the easiest ways to waste hackathon hours.

## Repo conventions

- **Time alignment:** all data must land on a single timestamp grid keyed on `timestamp` (Europe/Athens, naive after `tz_localize(None)`). Hourly before 2025-10-01, **15-minute from 2025-10-01 onward**.
- **Look-ahead discipline:** every feature used to pick tomorrow's schedule must be available **before DAM gate closure (D-1 ≈ 12:00 EET)**. Realized values are for backtest labels and evaluation only. See the leakage rules in [DATA.md](DATA.md). This is the easiest mistake to make and the hardest to detect.
- **Units:** prices in `EUR/MWh`, energy in `MWh`, power in `MW`, durations in hours (`dt_t`). Suffix every column with its unit (`load_forecast_mw`, `dam_price_eur_mwh`).
- **Data caching:** `data_pipeline.download_file` already caches by output path. Pass `overwrite=True` to refetch. Don't re-roll your own downloader.
- **Filenames in `data/raw/`:** `YYYY-MM-DD_<source>.<ext>`. Filenames in `data/processed/`: `YYYY-MM-DD_<artefact>.csv`.
- **No emojis in code or markdown.** No multi-paragraph docstrings. Comments only when the *why* is non-obvious.

## Working style

- Hackathon mode: **ship at every tier**. A working Tier 0 beats a half-built Tier 2. Don't refactor for a future tier until the current tier runs end-to-end.
- Prefer editing existing files. The repo is small; do not invent abstractions for symmetry.
- When you change a layer's behavior in a way that contradicts an existing spec file, **update the spec file in the same change** — agents read the docs, drift is poison.
- For ambiguous research calls (soft vs hard regimes, scenario count, λ_buffer, λ_CVaR), state your default in the relevant spec, then ask the user before changing it. These are judgment calls, not implementation details.

## What lives where

| Path | Purpose |
| --- | --- |
| `data_pipeline.py` | downloaders + parsers + daily aligned dataset builder |
| `data/raw/` | raw downloaded files (gitignored; cache) |
| `data/processed/` | aligned per-day CSVs |
| `Hackathon_final.docx.pdf` | original problem statement from organizers |
| `STRATEGY.md` | strategic thesis (the *what* and *why*) |
| `*.md` (others) | layer specs and roadmap (the *how*) |

Code that does not yet exist but is planned: `forecast/`, `optimizer/`, `backtest/`, `scripts/`. See [ARCHITECTURE.md](ARCHITECTURE.md) for the target layout.

## Things to ask before doing

- Anything that fetches from a paid/licensed source (TTF gas, EUA carbon historical depth).
- Anything that requires an API token the user hasn't provisioned (ENTSO-E).
- Switching the optimizer from LP to MILP (changes solver requirements).
- Introducing a new ML dependency (xgboost, lightgbm, torch). State the reason and the alternative.

## Things you can do without asking

- Add a new feature column to the aligned dataset, as long as it is documented in [DATA.md](DATA.md).
- Add a new baseline (idle, naive-rank, perfect-foresight) to the backtest.
- Tighten a parser to handle a new HEnEx/IPTO file variant.
- Update any `.md` to reflect a decision the user has confirmed in the conversation.
