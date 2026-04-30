const baseUrl =
  import.meta.env.VITE_BATTERY_CONFIG_API_URL?.replace(/\/api\/battery-config\/?$/, '') ??
  'http://127.0.0.1:8001';

const summaryUrl = `${baseUrl}/api/backtest/summary`;

export interface BacktestSummary {
  tier: number;
  lambda: number | null;
  source_path: string;
  days: number;
  start_date: string;
  end_date: string;
  profit_eur: number;
  annualized_profit_eur: number;
  throughput_mwh: number;
  throughput_gwh: number;
  cycles_per_day: number;
  win_rate: number;
  loss_rate: number;
  worst_day_eur: number;
  best_day_eur: number;
  cvar5_eur: number;
  max_drawdown_eur: number;
  pnl_sharpe_annualized: number;
  pnl_sortino_annualized: number;
  capex_eur: number;
  capex_per_mwh: number;
  energy_mwh: number;
  risk_free_rate_pct: number;
  annualized_return_pct: number;
  annualized_excess_return_pct: number;
  life_years_6000c: number;
  life_years_8000c: number;
  forecast_vs_realized_eur: number | null;
  expected_p50_profit_eur: number | null;
}

export interface BacktestQuery {
  tier: number;
  lambda?: number | null;
  capexPerMwh?: number;
  energyMwh?: number;
  rfPct?: number;
}

export async function fetchBacktestSummary(q: BacktestQuery): Promise<BacktestSummary> {
  const params = new URLSearchParams();
  params.set('tier', String(q.tier));
  if (q.lambda !== undefined && q.lambda !== null) params.set('lambda', String(q.lambda));
  if (q.capexPerMwh !== undefined) params.set('capex_per_mwh', String(q.capexPerMwh));
  if (q.energyMwh !== undefined) params.set('energy_mwh', String(q.energyMwh));
  if (q.rfPct !== undefined) params.set('rf_pct', String(q.rfPct));

  const res = await fetch(`${summaryUrl}?${params.toString()}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Backtest summary ${res.status}: ${body}`);
  }
  return (await res.json()) as BacktestSummary;
}
