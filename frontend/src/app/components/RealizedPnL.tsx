import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, CalendarDays, CheckCircle2, Download, Play, RefreshCw, Wallet } from 'lucide-react';
import {
  fetchFromHenex,
  loadAvailableDates,
  loadRealizedPnl,
  runOptimiserForDate,
  waitForOptimiser,
  type RealizedPnlMtuRow,
  type RealizedPnlResponse,
} from '../data/realizedPnlApi';

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const eur = (n: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

const eurDetailed = (n: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 }).format(n);

const num = (n: number, digits = 2) =>
  new Intl.NumberFormat('en-IE', { maximumFractionDigits: digits }).format(n);

const tooltipStyle = {
  backgroundColor: '#0F1720',
  border: '1px solid rgba(148,163,184,0.22)',
  borderRadius: '6px',
  color: '#fff',
};

function timeLabel(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function DateControls(props: {
  selectedDate: string;
  onDateChange: (d: string) => void;
  onRun: () => void;
  onFetch: () => void;
  runBusy: boolean;
  henexBusy: boolean;
  runStatus: string | null;
  availableDates: string[];
}) {
  const { selectedDate, onDateChange, onRun, onFetch, runBusy, henexBusy, runStatus, availableDates } = props;
  const busy = runBusy || henexBusy;
  const minDate = availableDates.length ? availableDates[availableDates.length - 1] : '2025-01-01';
  const maxDate = availableDates.length ? availableDates[0] : todayIso();
  const isDateAvailable = !availableDates.length || availableDates.includes(selectedDate);

  return (
    <div className="surface-muted mt-4 rounded-md p-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="flex items-center gap-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">
            <CalendarDays className="h-3 w-3" />
            Delivery day
          </span>
          <select
            value={selectedDate}
            onChange={(e) => onDateChange(e.target.value)}
            disabled={busy || !availableDates.length}
            className="rounded border border-slate-700/60 bg-[#0F1720] px-2 py-1.5 text-sm text-slate-200 focus:border-[#9ed9c5]/60 focus:outline-none disabled:opacity-50"
          >
            {!availableDates.includes(selectedDate) && (
              <option value={selectedDate}>{selectedDate} (not on HEnEx)</option>
            )}
            {availableDates.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Or pick any
          </span>
          <input
            type="date"
            value={selectedDate}
            min={minDate}
            max={maxDate}
            onChange={(e) => onDateChange(e.target.value)}
            disabled={busy}
            className="rounded border border-slate-700/60 bg-[#0F1720] px-2 py-1.5 text-sm text-slate-200 focus:border-[#9ed9c5]/60 focus:outline-none disabled:opacity-50"
          />
        </label>
        <button
          onClick={onRun}
          disabled={busy || !selectedDate || !isDateAvailable}
          title={isDateAvailable ? '' : 'HEnEx has not published this date'}
          className="inline-flex items-center gap-2 rounded border border-[#9ed9c5]/40 bg-[#9ed9c5]/10 px-3 py-1.5 text-sm text-[#bcebdc] hover:bg-[#9ed9c5]/15 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {runBusy ? 'Running…' : 'Run optimiser + fetch HEnEx'}
        </button>
        <button
          onClick={onFetch}
          disabled={busy || !selectedDate || !isDateAvailable}
          className="inline-flex items-center gap-2 rounded border border-slate-700/60 bg-[#141c24] px-3 py-1.5 text-sm text-slate-200 hover:bg-[#1a242e] disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {henexBusy ? 'Fetching…' : 'Fetch HEnEx only'}
        </button>
      </div>
      <div className="mt-3 text-xs text-slate-500">
        {availableDates.length
          ? `HEnEx available: ${minDate} → ${maxDate} (${availableDates.length} days). Older dates require ENTSO-E API.`
          : 'Loading available HEnEx dates…'}
      </div>
      {runStatus && (
        <div className="mt-1 text-xs text-slate-400">{runStatus}</div>
      )}
      {!isDateAvailable && (
        <div className="mt-1 text-xs text-amber-300">
          Selected date is outside HEnEx public listing — fetch will fail.
        </div>
      )}
    </div>
  );
}

export function RealizedPnL() {
  const [data, setData] = useState<RealizedPnlResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [henexBusy, setHenexBusy] = useState(false);
  const [henexInfo, setHenexInfo] = useState<{ source: string; date: string } | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(todayIso());
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  const [availableDates, setAvailableDates] = useState<string[]>([]);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await loadRealizedPnl();
      setData(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const fetchHenex = async (deliveryDay?: string) => {
    setHenexBusy(true);
    setError(null);
    try {
      const r = await fetchFromHenex(deliveryDay);
      setHenexInfo({ source: r.source_url, date: r.delivery_day });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setHenexBusy(false);
    }
  };

  const runForDate = async (deliveryDay: string) => {
    setRunBusy(true);
    setError(null);
    setRunStatus(`Generating forecast and running optimiser for ${deliveryDay}…`);
    try {
      await runOptimiserForDate(deliveryDay);
      await waitForOptimiser();
      setRunStatus(`Fetching HEnEx DAM clearing for ${deliveryDay}…`);
      const r = await fetchFromHenex(deliveryDay);
      setHenexInfo({ source: r.source_url, date: r.delivery_day });
      await refresh();
      setRunStatus(`Done — evaluation complete for ${deliveryDay}`);
    } catch (e) {
      setError((e as Error).message);
      setRunStatus(null);
    } finally {
      setRunBusy(false);
    }
  };

  useEffect(() => {
    refresh();
    loadAvailableDates()
      .then((dates) => {
        setAvailableDates(dates);
        if (dates.length && !data?.summary?.delivery_day) {
          setSelectedDate(dates[0]);
        }
      })
      .catch(() => setAvailableDates([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (data?.summary?.delivery_day) setSelectedDate(data.summary.delivery_day);
  }, [data?.summary?.delivery_day]);

  const chartData = useMemo(() => {
    if (!data?.mtu) return [];
    return data.mtu.map((row) => ({
      ...row,
      time: timeLabel(row.timestamp),
      discharge_neg_mw: -row.discharge_mw,
    }));
  }, [data]);

  if (loading && !data) {
    return (
      <div className="mx-auto max-w-7xl p-4 md:p-8">
        <div className="surface rounded-md p-8 text-center text-slate-400">Loading realized PnL…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-7xl p-4 md:p-8">
        <div className="surface rounded-md p-8 text-center">
          <div className="mb-2 text-sm text-rose-300">Failed to load realized PnL</div>
          <div className="text-xs text-slate-500">{error}</div>
          <button
            onClick={refresh}
            className="mt-4 inline-flex items-center gap-2 rounded border border-slate-700/60 bg-[#141c24] px-3 py-1.5 text-sm text-slate-200 hover:bg-[#1a242e]"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data?.available) {
    return (
      <div className="mx-auto max-w-7xl p-4 md:p-8">
        <div className="surface rounded-md p-8">
          <div className="flex items-center gap-3 text-amber-200">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-semibold">Awaiting DAM clearing prices…</span>
          </div>
          <p className="mt-3 max-w-2xl text-sm text-slate-400">
            {data?.message ??
              'No realized PnL evaluation found yet. After HEnEx publishes the actual DAM prices around 15:00 D-1, run optimisation/realized_pnl.py to evaluate the tier_final schedule against them.'}
          </p>
          <DateControls
            selectedDate={selectedDate}
            onDateChange={setSelectedDate}
            onRun={() => runForDate(selectedDate)}
            onFetch={() => fetchHenex(selectedDate)}
            runBusy={runBusy}
            henexBusy={henexBusy}
            runStatus={runStatus}
            availableDates={availableDates}
          />
          <button
            onClick={refresh}
            className="mt-3 inline-flex items-center gap-2 rounded border border-slate-700/60 bg-[#141c24] px-3 py-1.5 text-sm text-slate-200 hover:bg-[#1a242e]"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Check again
          </button>
        </div>
      </div>
    );
  }

  const s = data.summary!;
  const pnlTone = s.realized_pnl_eur >= 0 ? 'text-[#bcebdc]' : 'text-rose-300';
  const deltaTone = s.forecast_vs_realized_delta_eur >= 0 ? 'text-[#bcebdc]' : 'text-amber-200';
  const violationTone = s.violations_total === 0 ? 'text-[#bcebdc]' : 'text-rose-300';

  const kpis = [
    { label: 'Realized PnL', value: eur(s.realized_pnl_eur), note: `${num(s.mtus_total)} MTUs evaluated`, tone: pnlTone },
    { label: 'Net arbitrage', value: eur(s.net_arbitrage_profit_eur), note: `Charge ${eur(-s.total_charge_cost_eur)} · Discharge ${eur(s.total_discharge_revenue_eur)}`, tone: 'text-slate-300' },
    { label: 'Degradation', value: eur(-s.degradation_cost_eur), note: `${num(s.throughput_mwh)} MWh throughput · ${num(s.equivalent_cycles)} cycles`, tone: 'text-slate-300' },
    { label: 'Forecast Δ', value: `${s.forecast_vs_realized_delta_eur >= 0 ? '+' : ''}${eur(s.forecast_vs_realized_delta_eur)}`, note: `MAE ${num(s.mean_abs_price_error_eur_mwh)} €/MWh`, tone: deltaTone },
  ];

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-slate-500">
            <Wallet className="h-4 w-4" />
            Realized PnL · Day-Ahead Reconciliation
          </div>
          <h1 className="text-3xl font-semibold leading-tight text-white">
            {s.delivery_day ?? 'Delivery day'} — tier_final schedule vs actual DAM
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            Post-clearing evaluation of the optimiser schedule. No re-optimisation, no order submission — actual HEnEx DAM prices applied to the dispatched MWh.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => fetchHenex(s.delivery_day ?? undefined)}
            disabled={henexBusy}
            className="inline-flex items-center gap-2 rounded border border-[#9ed9c5]/40 bg-[#9ed9c5]/10 px-3 py-1.5 text-sm text-[#bcebdc] hover:bg-[#9ed9c5]/15 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            {henexBusy ? 'Fetching…' : 'Re-fetch from HEnEx'}
          </button>
          <button
            onClick={refresh}
            className="inline-flex items-center gap-2 rounded border border-slate-700/60 bg-[#141c24] px-3 py-1.5 text-sm text-slate-200 hover:bg-[#1a242e]"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>
      <DateControls
        selectedDate={selectedDate}
        onDateChange={setSelectedDate}
        onRun={() => runForDate(selectedDate)}
        onFetch={() => fetchHenex(selectedDate)}
        runBusy={runBusy}
        henexBusy={henexBusy}
        runStatus={runStatus}
        availableDates={availableDates}
      />
      {henexInfo && (
        <div className="mt-3 mb-6 rounded border border-[#9ed9c5]/30 bg-[#9ed9c5]/5 px-3 py-2 text-xs text-slate-300">
          Loaded HEnEx DAM for <span className="font-semibold text-white">{henexInfo.date}</span> ·{' '}
          <a href={henexInfo.source} target="_blank" rel="noreferrer" className="text-[#bcebdc] underline-offset-2 hover:underline">
            source XLSX
          </a>
        </div>
      )}

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <div key={k.label} className="border-l border-slate-700/70 pl-4">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{k.label}</div>
            <div className={`mt-2 text-2xl font-semibold ${k.tone}`}>{k.value}</div>
            <div className="mt-1 text-xs text-slate-400">{k.note}</div>
          </div>
        ))}
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="surface-muted rounded-md p-4">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">SOC range</div>
          <div className="mt-1 text-lg font-semibold text-white">
            {num(s.min_soc_mwh)} – {num(s.max_soc_mwh)} MWh
          </div>
        </div>
        <div className="surface-muted rounded-md p-4">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">Throughput</div>
          <div className="mt-1 text-lg font-semibold text-white">{num(s.throughput_mwh)} MWh</div>
          <div className="text-xs text-slate-500">{num(s.equivalent_cycles)} equivalent cycles</div>
        </div>
        <div className="surface-muted rounded-md p-4">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">Expected (P50)</div>
          <div className="mt-1 text-lg font-semibold text-white">{eur(s.expected_pnl_on_p50_eur)}</div>
          <div className="text-xs text-slate-500">vs realized {eur(s.realized_pnl_eur)}</div>
        </div>
        <div className="surface-muted rounded-md p-4">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">Violations</div>
          <div className={`mt-1 text-lg font-semibold ${violationTone}`}>
            {s.violations_total === 0 ? 'None' : `${s.violations_total} flags`}
          </div>
          <div className="text-xs text-slate-500">
            SOC<sub>&lt;min</sub> {s.viol_soc_below_min} · SOC<sub>&gt;max</sub> {s.viol_soc_above_max} · simul {s.viol_simultaneous} · power {s.viol_power_exceeded}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="surface rounded-md p-5">
          <div className="mb-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Prices</div>
            <h2 className="text-base font-semibold text-white">Forecast P50 vs actual DAM clearing</h2>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
              <XAxis dataKey="time" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} interval={11} />
              <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={40} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${num(v, 1)} €/MWh`} />
              <Line type="monotone" dataKey="p50_eur_mwh" stroke="#9ed9c5" strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Forecast P50" />
              <Line type="monotone" dataKey="actual_price_eur_mwh" stroke="#6EE7B7" strokeWidth={2} dot={false} name="Actual DAM" />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className="surface rounded-md p-5">
          <div className="mb-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Dispatch</div>
            <h2 className="text-base font-semibold text-white">Charge / discharge per 15-min MTU</h2>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} stackOffset="sign">
              <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
              <XAxis dataKey="time" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} interval={11} />
              <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={40} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${num(Math.abs(v), 2)} MW`} />
              <ReferenceLine y={0} stroke="#475569" />
              <Bar dataKey="charge_mw" fill="#FB7185" name="Charge" />
              <Bar dataKey="discharge_neg_mw" fill="#6EE7B7" name="Discharge" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="surface rounded-md p-5">
          <div className="mb-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">SOC trajectory</div>
            <h2 className="text-base font-semibold text-white">State of charge through the day</h2>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
              <XAxis dataKey="time" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} interval={11} />
              <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={40} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${num(v, 2)} MWh`} />
              <Line type="monotone" dataKey="soc_mwh_recomputed" stroke="#9ed9c5" strokeWidth={2} dot={false} name="SOC" />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className="surface rounded-md p-5">
          <div className="mb-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Cumulative PnL</div>
            <h2 className="text-base font-semibold text-white">Realized cashflow accumulating intraday</h2>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6EE7B7" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#6EE7B7" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
              <XAxis dataKey="time" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} interval={11} />
              <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={50} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => eurDetailed(v)} />
              <ReferenceLine y={0} stroke="#475569" />
              <Area type="monotone" dataKey="cum_realized_pnl_eur" stroke="#6EE7B7" strokeWidth={2} fill="url(#pnlGradient)" name="Cumulative PnL" />
            </AreaChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="mt-6 surface rounded-md p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">MTU breakdown</div>
            <h2 className="text-base font-semibold text-white">15-minute realized cashflows</h2>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <CheckCircle2 className="h-3.5 w-3.5 text-[#9ed9c5]" />
            {data.mtu.length} rows
          </div>
        </div>
        <div className="max-h-[420px] overflow-auto rounded border border-slate-700/40">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-[#0F1720] text-slate-500 uppercase tracking-[0.1em]">
              <tr>
                <th className="px-3 py-2">MTU</th>
                <th className="px-3 py-2 text-right">Forecast</th>
                <th className="px-3 py-2 text-right">Actual</th>
                <th className="px-3 py-2 text-right">Charge MW</th>
                <th className="px-3 py-2 text-right">Discharge MW</th>
                <th className="px-3 py-2 text-right">Cashflow €</th>
                <th className="px-3 py-2 text-right">Degr. €</th>
                <th className="px-3 py-2 text-right">Realized €</th>
                <th className="px-3 py-2 text-right">SOC MWh</th>
                <th className="px-3 py-2">Flags</th>
              </tr>
            </thead>
            <tbody>
              {data.mtu.map((row: RealizedPnlMtuRow) => {
                const flags: string[] = [];
                if (row.flag_soc_below_min) flags.push('SOC<min');
                if (row.flag_soc_above_max) flags.push('SOC>max');
                if (row.flag_simultaneous) flags.push('simul');
                if (row.flag_power_exceeded) flags.push('power');
                if (row.flag_grid_import) flags.push('import');
                if (row.flag_grid_export) flags.push('export');
                const realizedTone = row.realized_pnl_eur >= 0 ? 'text-[#bcebdc]' : 'text-rose-300';
                return (
                  <tr key={row.timestamp} className="border-t border-slate-700/30 hover:bg-white/[0.02]">
                    <td className="px-3 py-1.5 font-mono text-slate-300">{timeLabel(row.timestamp)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-400">{num(row.p50_eur_mwh, 1)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-200">{num(row.actual_price_eur_mwh, 1)}</td>
                    <td className="px-3 py-1.5 text-right">{row.charge_mw > 1e-6 ? num(row.charge_mw, 2) : '·'}</td>
                    <td className="px-3 py-1.5 text-right">{row.discharge_mw > 1e-6 ? num(row.discharge_mw, 2) : '·'}</td>
                    <td className="px-3 py-1.5 text-right">{eurDetailed(row.net_cashflow_eur)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-500">{eurDetailed(-row.degradation_eur)}</td>
                    <td className={`px-3 py-1.5 text-right font-semibold ${realizedTone}`}>{eurDetailed(row.realized_pnl_eur)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-300">{num(row.soc_mwh_recomputed, 2)}</td>
                    <td className="px-3 py-1.5">
                      {flags.length === 0 ? (
                        <span className="text-slate-600">·</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-rose-500/10 px-1.5 py-0.5 text-[0.65rem] text-rose-300">
                          <AlertTriangle className="h-3 w-3" />
                          {flags.join(', ')}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
