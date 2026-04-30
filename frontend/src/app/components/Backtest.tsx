import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, CheckCircle2, FileText, TrendingUp } from 'lucide-react';

const profitOverTime = [
  { date: 'Jan 1', profit: 2100 },
  { date: 'Jan 8', profit: 2450 },
  { date: 'Jan 15', profit: 2800 },
  { date: 'Jan 22', profit: 2650 },
  { date: 'Jan 29', profit: 3100 },
  { date: 'Feb 5', profit: 2900 },
  { date: 'Feb 12', profit: 3350 },
  { date: 'Feb 19', profit: 3800 },
  { date: 'Feb 26', profit: 3500 },
  { date: 'Mar 5', profit: 4200 },
  { date: 'Mar 12', profit: 3900 },
  { date: 'Mar 19', profit: 4500 },
];

const dailyProfitDistribution = [
  { range: '0-500', count: 12 },
  { range: '500-1000', count: 25 },
  { range: '1000-1500', count: 35 },
  { range: '1500-2000', count: 45 },
  { range: '2000-2500', count: 52 },
  { range: '2500-3000', count: 38 },
  { range: '3000-3500', count: 22 },
  { range: '3500+', count: 15 },
];

const drawdownData = [
  { date: 'Week 1', drawdown: 0 },
  { date: 'Week 2', drawdown: -150 },
  { date: 'Week 3', drawdown: -80 },
  { date: 'Week 4', drawdown: -220 },
  { date: 'Week 5', drawdown: -100 },
  { date: 'Week 6', drawdown: -380 },
  { date: 'Week 7', drawdown: -200 },
  { date: 'Week 8', drawdown: -120 },
  { date: 'Week 9', drawdown: -290 },
  { date: 'Week 10', drawdown: -150 },
  { date: 'Week 11', drawdown: -90 },
  { date: 'Week 12', drawdown: -50 },
];

const kpis = [
  { label: 'Net margin', value: '€308,450', note: '+15.2% vs forecast', tone: 'positive' },
  { label: 'Daily average', value: '€3,427', note: '90 day sample', tone: 'neutral' },
  { label: 'Profitable trades', value: '87.3%', note: '262 of 300 trades', tone: 'positive' },
  { label: 'Worst drawdown', value: '€380', note: '-0.12% of gross', tone: 'warning' },
];

const replayRows = [
  { period: 'Jan', trades: 98, margin: '€94,200', hitRate: '84%', note: 'Two weak evening spreads' },
  { period: 'Feb', trades: 94, margin: '€101,850', hitRate: '89%', note: 'Stable overnight charge windows' },
  { period: 'Mar', trades: 108, margin: '€112,400', hitRate: '89%', note: 'Best volatility capture' },
];

export function Backtest() {
  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <div className="mb-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="border-b border-slate-700/50 pb-6 xl:border-b-0 xl:pb-0">
          <div className="mb-3 flex items-center gap-2 text-sm text-slate-500">
            <FileText className="h-4 w-4" />
            Backtest / Rolling 90 days / HENEX DAM
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white">
            Replay shows the fleet earns its keep when evening spreads widen.
          </h1>
          <p className="mt-4 max-w-2xl text-slate-400">
            A 300-trade replay using recorded day-ahead prices, degradation costs, and the current 40 MWh plant limits.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {kpis.map((item) => (
              <div key={item.label} className="border-l border-slate-700/70 pl-4">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{item.label}</div>
                <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
                <div
                  className={`mt-1 flex items-center gap-1 text-xs ${
                    item.tone === 'positive'
                      ? 'text-[#bcebdc]'
                      : item.tone === 'warning'
                      ? 'text-amber-200'
                      : 'text-slate-400'
                  }`}
                >
                  {item.tone === 'warning' ? <AlertTriangle className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                  {item.note}
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="surface-muted rounded-md p-5">
          <div className="mb-4 text-sm font-semibold text-white">Replay assumptions</div>
          <div className="space-y-3 text-sm">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#9ed9c5]" />
              <span className="text-slate-300">40 MWh available capacity, 5 MW power limit</span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#9ed9c5]" />
              <span className="text-slate-300">Round-trip efficiency held at 82.8%</span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 text-[#9ed9c5]" />
              <span className="text-slate-300">Trades below €20/MWh spread are ignored</span>
            </div>
          </div>
          <div className="mt-5 border-t border-slate-700/50 pt-4 text-xs leading-relaxed text-slate-500">
            This is a replay, not a prediction. It is meant to expose how the dispatch rule behaves under actual historical price shape.
          </div>
        </aside>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="surface rounded-md p-5 md:p-6">
          <div className="mb-5 flex flex-col gap-1 border-b border-slate-700/50 pb-4">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Cumulative replay</div>
            <h2 className="text-lg font-semibold text-white">Margin built steadily, with two shallow pullbacks</h2>
          </div>
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={profitOverTime}>
              <defs>
                <linearGradient id="profitLineGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
              <XAxis dataKey="date" stroke="#475569" tick={{ fill: '#94A3B8' }} />
              <YAxis stroke="#475569" tick={{ fill: '#94A3B8' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0F1720',
                  border: '1px solid rgba(148,163,184,0.22)',
                  borderRadius: '6px',
                  color: '#fff'
                }}
              />
              <Line
                type="monotone"
                dataKey="profit"
                stroke="#6EE7B7"
                strokeWidth={3}
                dot={{ fill: '#6EE7B7', r: 4 }}
                fill="url(#profitLineGradient)"
              />
            </LineChart>
          </ResponsiveContainer>

          <div className="mt-5 grid gap-3 border-t border-slate-700/50 pt-4 text-sm md:grid-cols-3">
            {replayRows.map((row) => (
              <div key={row.period} className="rounded border border-slate-700/40 bg-black/10 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold text-white">{row.period}</span>
                  <span className="text-xs text-slate-500">{row.trades} trades</span>
                </div>
                <div className="text-lg font-semibold text-[#d9fff2]">{row.margin}</div>
                <div className="mt-1 text-xs text-slate-400">{row.hitRate} hit rate · {row.note}</div>
              </div>
            ))}
          </div>
        </section>

        <div className="space-y-6">
          <section className="surface rounded-md p-5">
            <div className="mb-4">
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Distribution</div>
              <h2 className="mt-1 text-base font-semibold text-white">Most days land between €1.5k and €3k</h2>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={dailyProfitDistribution}>
                <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
                <XAxis dataKey="range" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} />
                <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={28} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0F1720',
                    border: '1px solid rgba(148,163,184,0.22)',
                    borderRadius: '6px',
                    color: '#fff'
                  }}
                />
                <Bar dataKey="count" fill="#9ed9c5" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </section>

          <section className="surface rounded-md p-5">
            <div className="mb-4">
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Risk trace</div>
              <h2 className="mt-1 text-base font-semibold text-white">Drawdown remained contained</h2>
            </div>
            <ResponsiveContainer width="100%" height={190}>
              <LineChart data={drawdownData}>
                <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
                <XAxis dataKey="date" stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} />
                <YAxis stroke="#475569" tick={{ fill: '#94A3B8', fontSize: 11 }} width={34} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0F1720',
                    border: '1px solid rgba(148,163,184,0.22)',
                    borderRadius: '6px',
                    color: '#fff'
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="drawdown"
                  stroke="#FB7185"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </section>
        </div>
      </div>
    </div>
  );
}
