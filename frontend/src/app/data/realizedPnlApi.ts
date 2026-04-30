const baseUrl =
  import.meta.env.VITE_BATTERY_CONFIG_API_URL?.replace(/\/api\/battery-config\/?$/, '') ??
  'http://127.0.0.1:8001';

const realizedPnlUrl = `${baseUrl}/api/realized-pnl`;
const realizedPnlFetchUrl = `${baseUrl}/api/realized-pnl/fetch`;

export interface RealizedPnlSummary {
  delivery_day: string | null;
  mtus_total: number;
  mtus_missing_actual: number;
  total_charge_cost_eur: number;
  total_discharge_revenue_eur: number;
  net_arbitrage_profit_eur: number;
  degradation_cost_eur: number;
  realized_pnl_eur: number;
  expected_pnl_on_p50_eur: number;
  forecast_vs_realized_delta_eur: number;
  throughput_mwh: number;
  equivalent_cycles: number;
  mean_abs_price_error_eur_mwh: number;
  min_soc_mwh: number;
  max_soc_mwh: number;
  violations_total: number;
  viol_soc_below_min: number;
  viol_soc_above_max: number;
  viol_simultaneous: number;
  viol_power_exceeded: number;
  viol_grid_import: number;
  viol_grid_export: number;
  cycle_limit_breach: boolean;
}

export interface RealizedPnlMtuRow {
  timestamp: string;
  p10_eur_mwh?: number;
  p50_eur_mwh: number;
  p90_eur_mwh?: number;
  charge_mw: number;
  discharge_mw: number;
  actual_price_eur_mwh: number;
  price_error_eur_mwh: number;
  charge_cost_eur: number;
  discharge_revenue_eur: number;
  net_cashflow_eur: number;
  degradation_eur: number;
  realized_pnl_eur: number;
  cum_realized_pnl_eur: number;
  soc_mwh_recomputed: number;
  soc_mwh_schedule: number;
  flag_soc_below_min: boolean;
  flag_soc_above_max: boolean;
  flag_simultaneous: boolean;
  flag_power_exceeded: boolean;
  flag_grid_import: boolean;
  flag_grid_export: boolean;
}

export interface RealizedPnlResponse {
  available: boolean;
  message?: string;
  summary: RealizedPnlSummary | null;
  mtu: RealizedPnlMtuRow[];
}

export async function loadRealizedPnl(): Promise<RealizedPnlResponse> {
  const response = await fetch(realizedPnlUrl);
  if (!response.ok) {
    throw new Error(`Realized PnL API returned ${response.status}`);
  }
  return response.json() as Promise<RealizedPnlResponse>;
}

export interface FetchHenexResult {
  ok: boolean;
  delivery_day: string;
  source_url: string;
  csv_path: string;
  summary: RealizedPnlSummary | null;
}

export async function fetchFromHenex(deliveryDay?: string): Promise<FetchHenexResult> {
  const response = await fetch(realizedPnlFetchUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(deliveryDay ? { date: deliveryDay } : {}),
  });
  const json = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(json?.error ?? `HEnEx fetch failed: ${response.status}`);
  }
  return json as FetchHenexResult;
}

const optimiseRunUrl = `${baseUrl}/api/optimise/run`;
const optimiseStatusUrl = `${baseUrl}/api/optimise/status`;

export interface OptimiseStatus {
  running: boolean;
  last_run_started: string | null;
  last_run_finished: string | null;
  last_exit_code: number | null;
  last_error: string | null;
  last_target_date?: string | null;
  next_run_at: string | null;
}

export async function runOptimiserForDate(deliveryDay?: string): Promise<void> {
  const response = await fetch(optimiseRunUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(deliveryDay ? { date: deliveryDay } : {}),
  });
  const json = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(json?.error ?? `Optimiser run failed: ${response.status}`);
  }
}

export async function pollOptimiserStatus(): Promise<OptimiseStatus> {
  const response = await fetch(optimiseStatusUrl);
  if (!response.ok) {
    throw new Error(`Status poll failed: ${response.status}`);
  }
  return response.json() as Promise<OptimiseStatus>;
}

const availableDatesUrl = `${baseUrl}/api/dam/available-dates`;

export async function loadAvailableDates(): Promise<string[]> {
  const response = await fetch(availableDatesUrl);
  if (!response.ok) {
    throw new Error(`available-dates failed: ${response.status}`);
  }
  const json = (await response.json()) as { dates: string[] };
  return json.dates ?? [];
}

export async function waitForOptimiser(timeoutMs = 120000): Promise<OptimiseStatus> {
  const start = Date.now();
  for (;;) {
    const s = await pollOptimiserStatus();
    if (!s.running && s.last_run_finished) return s;
    if (Date.now() - start > timeoutMs) {
      throw new Error('Optimiser run timed out');
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}
