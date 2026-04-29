import { useState } from 'react';
import { Battery, TrendingUp } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const previewData = [
  { hour: '0', profit: 0 },
  { hour: '3', profit: 245 },
  { hour: '6', profit: 380 },
  { hour: '9', profit: 890 },
  { hour: '12', profit: 1450 },
  { hour: '15', profit: 1890 },
  { hour: '18', profit: 2375 },
  { hour: '21', profit: 2240 },
  { hour: '24', profit: 2375 },
];

export function BatteryConfig() {
  const [config, setConfig] = useState({
    batteries: 4,
    capacity: 10,
    power: 5,
    chargeEff: 92,
    dischargeEff: 90,
    degradationCost: 2.5,
    mode: 'aggressive'
  });

  const estimatedProfit = Math.round(config.batteries * config.capacity * 23.75 * (config.mode === 'aggressive' ? 1.2 : 0.9));

  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <div className="eyebrow mb-3">Asset setup</div>
        <h1 className="mb-2 text-3xl font-semibold text-white">Battery fleet</h1>
        <p className="text-slate-400">Tune plant limits, efficiencies, and trading posture before dispatch.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Left Side - Form */}
        <div className="surface rounded-lg p-6">
          <h3 className="mb-6 flex items-center gap-2 text-white">
            <Battery className="w-5 h-5" />
            Plant parameters
          </h3>

          <div className="space-y-6">
            <div>
              <label className="mb-2 block text-sm text-slate-400">Number of batteries</label>
              <input
                type="number"
                value={config.batteries}
                onChange={(e) => setConfig({ ...config, batteries: parseInt(e.target.value) })}
                className="field-control"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm text-slate-400">Capacity per unit (MWh)</label>
              <input
                type="number"
                value={config.capacity}
                onChange={(e) => setConfig({ ...config, capacity: parseFloat(e.target.value) })}
                className="field-control"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm text-slate-400">Power limit (MW)</label>
              <input
                type="number"
                value={config.power}
                onChange={(e) => setConfig({ ...config, power: parseFloat(e.target.value) })}
                className="field-control"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm text-slate-400">Charge efficiency (%)</label>
                <input
                  type="number"
                  value={config.chargeEff}
                  onChange={(e) => setConfig({ ...config, chargeEff: parseFloat(e.target.value) })}
                  className="field-control"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm text-slate-400">Discharge efficiency (%)</label>
                <input
                  type="number"
                  value={config.dischargeEff}
                  onChange={(e) => setConfig({ ...config, dischargeEff: parseFloat(e.target.value) })}
                  className="field-control"
                />
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm text-slate-400">Degradation cost (€/MWh)</label>
              <input
                type="number"
                step="0.1"
                value={config.degradationCost}
                onChange={(e) => setConfig({ ...config, degradationCost: parseFloat(e.target.value) })}
                className="field-control"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm text-slate-400">Trading posture</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfig({ ...config, mode: 'conservative' })}
                  className={`flex-1 py-3 px-4 rounded-lg transition-all ${
                    config.mode === 'conservative'
                      ? 'border border-sky-300/50 bg-sky-300/15 text-sky-100'
                      : 'border border-slate-700/50 bg-white/[0.03] text-slate-400 hover:bg-white/[0.06]'
                  }`}
                >
                  Conservative
                </button>
                <button
                  onClick={() => setConfig({ ...config, mode: 'aggressive' })}
                  className={`flex-1 py-3 px-4 rounded-lg transition-all ${
                    config.mode === 'aggressive'
                      ? 'border border-amber-300/50 bg-amber-300/15 text-amber-100'
                      : 'border border-slate-700/50 bg-white/[0.03] text-slate-400 hover:bg-white/[0.06]'
                  }`}
                >
                  Aggressive
                </button>
              </div>
            </div>

            <button className="w-full rounded-lg border border-emerald-300/40 bg-emerald-300/15 px-4 py-3 text-emerald-100 transition-colors hover:bg-emerald-300/20">
              Save fleet setup
            </button>
          </div>
        </div>

        {/* Right Side - Preview */}
        <div className="space-y-6">
          <div className="surface rounded-lg p-6">
            <h3 className="mb-4 flex items-center gap-2 text-white">
              <TrendingUp className="w-5 h-5" />
              Dispatch preview
            </h3>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-emerald-300/25 bg-emerald-300/10 p-4">
                <div className="mb-1 text-sm text-emerald-200">Daily margin</div>
                <div className="text-2xl text-white">€{estimatedProfit.toLocaleString()}</div>
              </div>
              <div className="rounded-lg border border-sky-300/25 bg-sky-300/10 p-4">
                <div className="mb-1 text-sm text-sky-200">Total capacity</div>
                <div className="text-2xl text-white">{config.batteries * config.capacity} MWh</div>
              </div>
            </div>

            <div className="mb-2 text-sm text-slate-400">Margin trajectory</div>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={previewData}>
                <defs>
                  <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
                <XAxis dataKey="hour" stroke="#475569" tick={{ fill: '#94A3B8' }} />
                <YAxis stroke="#475569" tick={{ fill: '#94A3B8' }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0F1720',
                    border: '1px solid rgba(148,163,184,0.22)',
                    borderRadius: '6px',
                    color: '#fff'
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="profit"
                  stroke="#10B981"
                  strokeWidth={2}
                  fill="url(#profitGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="surface rounded-lg p-6">
            <h3 className="text-white mb-4">System Summary</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">Round-trip efficiency</span>
                <span className="text-white">{((config.chargeEff * config.dischargeEff) / 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Max daily cycles</span>
                <span className="text-white">{Math.floor(24 / (config.capacity / config.power))}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Degradation per cycle</span>
                <span className="text-white">€{(config.degradationCost * config.capacity * config.batteries).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Trading posture</span>
                <span className={config.mode === 'aggressive' ? 'text-amber-200' : 'text-sky-200'}>
                  {config.mode.charAt(0).toUpperCase() + config.mode.slice(1)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
