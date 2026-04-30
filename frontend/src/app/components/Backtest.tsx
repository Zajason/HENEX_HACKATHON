import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, TrendingUp } from 'lucide-react';
import { fetchBacktestSummary, type BacktestSummary } from '../data/backtestApi';

// Which tiers + lambdas have precomputed runs on disk.
const TIER_OPTIONS: { tier: number; label: string; lambdas: number[] | null }[] = [
  { tier: 0, label: 'Tier 0 — Deterministic LP', lambdas: [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.35] },
  { tier: 1, label: 'Tier 1 — Regime CVaR (recommended)', lambdas: [0.10, 0.25, 0.50, 0.75] },
  { tier: 2, label: 'Tier 2 — Curve-aware CVaR', lambdas: null },
  { tier: 3, label: 'Tier 3 — Greek-structural CVaR', lambdas: [0.10, 0.25, 0.50, 0.75] },
];

const CAPEX_PRESETS = [
  { value: 200_000, label: '€200k/MWh — aggressive Chinese cell' },
  { value: 220_000, label: '€220k/MWh — modern LFP turnkey (default)' },
  { value: 250_000, label: '€250k/MWh — Greek market mid-range' },
  { value: 300_000, label: '€300k/MWh — premium / 2022 ref' },
];

const fmt = {
  eurMillions: (v: number) => `€${(v / 1e6).toFixed(2)}M`,
  eurThousands: (v: number) => `€${(v / 1e3).toFixed(1)}k`,
  eur0: (v: number) => `€${v.toLocaleString('en-EU', { maximumFractionDigits: 0 })}`,
  pct: (v: number, digits = 2) => `${v.toFixed(digits)}%`,
  ratio: (v: number, digits = 2) => v.toFixed(digits),
};

export function Backtest() {
  const [tier, setTier] = useState<number>(3);
  const [lambdaIdx, setLambdaIdx] = useState<number>(0);
  const [capexPerMwh, setCapexPerMwh] = useState<number>(220_000);

  const tierOption = TIER_OPTIONS.find((t) => t.tier === tier)!;
  const lambdaValue = tierOption.lambdas ? tierOption.lambdas[lambdaIdx] : null;

  // Reset slider when switching tier
  useEffect(() => {
    setLambdaIdx(0);
  }, [tier]);

  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState<boolean>(false);

  // Mark inputs as dirty whenever they change so the Run button highlights.
  useEffect(() => {
    setDirty(true);
  }, [tier, lambdaValue, capexPerMwh]);

  const runBacktest = () => {
    setLoading(true);
    setError(null);
    fetchBacktestSummary({ tier, lambda: lambdaValue, capexPerMwh })
      .then((s) => {
        setSummary(s);
        setDirty(false);
      })
      .catch((e) => {
        setError(String(e.message ?? e));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  // Auto-run on first mount.
  useEffect(() => {
    runBacktest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const headlineKpis = useMemo(() => {
    if (!summary) return [];
    return [
      {
        label: 'Realized profit (model)',
        value: fmt.eurMillions(summary.profit_eur),
        note: `${summary.days} days · ${summary.start_date} → ${summary.end_date}`,
        tone: 'positive' as const,
      },
      {
        label: 'Annualized return',
        value: fmt.pct(summary.annualized_return_pct),
        note: `Excess (rf=${summary.risk_free_rate_pct.toFixed(1)}%): ${fmt.pct(summary.annualized_excess_return_pct)}`,
        tone: 'positive' as const,
      },
      {
        label: 'PnL Sharpe (annual)',
        value: fmt.ratio(summary.pnl_sharpe_annualized),
        note: `Sortino: ${fmt.ratio(summary.pnl_sortino_annualized)}`,
        tone: 'positive' as const,
      },
      {
        label: 'Win rate',
        value: fmt.pct(summary.win_rate * 100, 1),
        note: `${(summary.win_rate * summary.days).toFixed(0)} / ${summary.days} days`,
        tone: summary.win_rate > 0.85 ? ('positive' as const) : ('neutral' as const),
      },
    ];
  }, [summary]);

  const lifecycleRows = useMemo(() => {
    if (!summary) return [];
    return [
      {
        label: 'Cycles / day',
        value: fmt.ratio(summary.cycles_per_day, 2),
      },
      {
        label: 'Throughput (annualized)',
        value: `${(summary.throughput_gwh * 365 / summary.days).toFixed(1)} GWh`,
      },
      {
        label: 'Battery life @ 6000c',
        value: `${summary.life_years_6000c.toFixed(1)} yrs`,
      },
      {
        label: 'Battery life @ 8000c (modern LFP)',
        value: `${summary.life_years_8000c.toFixed(1)} yrs`,
      },
    ];
  }, [summary]);

  const riskRows = useMemo(() => {
    if (!summary) return [];
    return [
      { label: 'CVaR-5% daily', value: fmt.eur0(summary.cvar5_eur) },
      { label: 'Max drawdown', value: fmt.eur0(summary.max_drawdown_eur) },
      { label: 'Worst day', value: fmt.eur0(summary.worst_day_eur) },
      { label: 'Best day', value: fmt.eur0(summary.best_day_eur) },
    ];
  }, [summary]);

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Backtest 2025</h1>
          <p className="text-sm text-muted-foreground">
            Walk-forward forecast → optimizer → realized DAM evaluation. Greek HEnEx 75 MW / 300 MWh battery.
          </p>
        </div>
        {loading ? (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" /> loading
          </span>
        ) : null}
      </header>

      {/* Controls */}
      <section className="mb-6 grid grid-cols-1 items-end gap-4 rounded-lg border bg-card p-4 md:grid-cols-4">
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Optimizer tier
          </label>
          <select
            value={tier}
            onChange={(e) => setTier(Number(e.target.value))}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            {TIER_OPTIONS.map((t) => (
              <option key={t.tier} value={t.tier}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            λ_risk{tierOption.lambdas ? ` — ${lambdaValue?.toFixed(2)}` : ' (single run on disk)'}
          </label>
          {tierOption.lambdas ? (
            <input
              type="range"
              min={0}
              max={tierOption.lambdas.length - 1}
              step={1}
              value={lambdaIdx}
              onChange={(e) => setLambdaIdx(Number(e.target.value))}
              className="mt-3 w-full"
            />
          ) : (
            <div className="mt-3 text-xs text-muted-foreground">
              Tier {tier} uses default λ. Run a sweep to enable this slider.
            </div>
          )}
          {tierOption.lambdas ? (
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              {tierOption.lambdas.map((l, i) => (
                <span key={i} className={i === lambdaIdx ? 'font-semibold text-foreground' : ''}>
                  {l.toFixed(2)}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            CAPEX €/MWh
          </label>
          <select
            value={capexPerMwh}
            onChange={(e) => setCapexPerMwh(Number(e.target.value))}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            {CAPEX_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <button
            type="button"
            onClick={runBacktest}
            disabled={loading}
            className={`w-full rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
              dirty
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-muted text-foreground hover:bg-muted/80'
            } disabled:opacity-50`}
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <RefreshCw className="h-4 w-4 animate-spin" /> running…
              </span>
            ) : dirty ? (
              'Run backtest'
            ) : (
              'Refresh'
            )}
          </button>
          {dirty && !loading ? (
            <div className="mt-1 text-[10px] text-muted-foreground">inputs changed — click to refresh</div>
          ) : null}
        </div>
      </section>

      {error ? (
        <div className="mb-6 flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4" />
          <div>
            <div className="font-medium">Failed to load backtest summary</div>
            <div className="mt-1 font-mono text-xs">{error}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Make sure <code>venv/bin/python -m api.server</code> is running on port 8001.
            </div>
          </div>
        </div>
      ) : null}

      {summary ? (
        <>
          <section className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {headlineKpis.map((k) => (
              <div key={k.label} className="rounded-lg border bg-card p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{k.label}</div>
                <div className="mt-1 text-2xl font-semibold">{k.value}</div>
                <div className="mt-1 text-xs text-muted-foreground">{k.note}</div>
              </div>
            ))}
          </section>

          <section className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border bg-card p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide">
                <TrendingUp className="h-4 w-4" /> Lifecycle & throughput
              </h2>
              <dl className="space-y-2 text-sm">
                {lifecycleRows.map((r) => (
                  <div key={r.label} className="flex items-center justify-between border-b border-border/50 pb-1.5 last:border-b-0">
                    <dt className="text-muted-foreground">{r.label}</dt>
                    <dd className="font-mono">{r.value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div className="rounded-lg border bg-card p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide">
                <AlertTriangle className="h-4 w-4" /> Risk
              </h2>
              <dl className="space-y-2 text-sm">
                {riskRows.map((r) => (
                  <div key={r.label} className="flex items-center justify-between border-b border-border/50 pb-1.5 last:border-b-0">
                    <dt className="text-muted-foreground">{r.label}</dt>
                    <dd className="font-mono">{r.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <section className="mb-6 rounded-lg border bg-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide">
              <CheckCircle2 className="h-4 w-4" /> Investment context
            </h2>
            <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-3">
              <div>
                <div className="text-muted-foreground">CAPEX</div>
                <div className="mt-0.5 font-mono">{fmt.eurMillions(summary.capex_eur)}</div>
                <div className="text-xs text-muted-foreground">
                  {summary.energy_mwh} MWh × {fmt.eur0(summary.capex_per_mwh)} / MWh
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">€/MW-year (DAM-only)</div>
                <div className="mt-0.5 font-mono">
                  {fmt.eurThousands(summary.annualized_profit_eur / 75)}
                </div>
                <div className="text-xs text-muted-foreground">
                  vs UK 2024 (€10-15k), DE 2024 (€40-60k)
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">Realistic Y1 cashflow</div>
                <div className="mt-0.5 font-mono">
                  {fmt.eurMillions(summary.annualized_profit_eur * 0.729 - 1.65e6)}
                </div>
                <div className="text-xs text-muted-foreground">
                  After 27% slippage/imbalance/leakage haircut + 2.5% OPEX
                </div>
              </div>
            </div>
          </section>

          <p className="text-xs text-muted-foreground">
            Source: <code className="font-mono">{summary.source_path.split('/').slice(-2).join('/')}</code> ·
            Sharpe is unit-free, identical for PnL and CAPEX-normalized return.
            Lower λ_risk = more aggressive cycling, fatter tail.
          </p>
        </>
      ) : null}
    </div>
  );
}
