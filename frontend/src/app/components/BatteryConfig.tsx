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
        <h1 className="text-3xl text-white mb-2">Battery Configuration</h1>
        <p className="text-gray-400">Configure your battery system parameters</p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Left Side - Form */}
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-6 flex items-center gap-2">
            <Battery className="w-5 h-5" />
            System Parameters
          </h3>

          <div className="space-y-6">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Number of Batteries</label>
              <input
                type="number"
                value={config.batteries}
                onChange={(e) => setConfig({ ...config, batteries: parseInt(e.target.value) })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-2 block">Capacity (MWh)</label>
              <input
                type="number"
                value={config.capacity}
                onChange={(e) => setConfig({ ...config, capacity: parseFloat(e.target.value) })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-2 block">Power (MW)</label>
              <input
                type="number"
                value={config.power}
                onChange={(e) => setConfig({ ...config, power: parseFloat(e.target.value) })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="text-sm text-gray-400 mb-2 block">Charge Efficiency (%)</label>
                <input
                  type="number"
                  value={config.chargeEff}
                  onChange={(e) => setConfig({ ...config, chargeEff: parseFloat(e.target.value) })}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400 mb-2 block">Discharge Efficiency (%)</label>
                <input
                  type="number"
                  value={config.dischargeEff}
                  onChange={(e) => setConfig({ ...config, dischargeEff: parseFloat(e.target.value) })}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-2 block">Degradation Cost (€/MWh)</label>
              <input
                type="number"
                step="0.1"
                value={config.degradationCost}
                onChange={(e) => setConfig({ ...config, degradationCost: parseFloat(e.target.value) })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-2 block">Trading Mode</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfig({ ...config, mode: 'conservative' })}
                  className={`flex-1 py-3 px-4 rounded-lg transition-all ${
                    config.mode === 'conservative'
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                      : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10'
                  }`}
                >
                  Conservative
                </button>
                <button
                  onClick={() => setConfig({ ...config, mode: 'aggressive' })}
                  className={`flex-1 py-3 px-4 rounded-lg transition-all ${
                    config.mode === 'aggressive'
                      ? 'bg-purple-500/20 text-purple-400 border border-purple-500/50'
                      : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10'
                  }`}
                >
                  Aggressive
                </button>
              </div>
            </div>

            <button className="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white py-3 px-4 rounded-lg hover:opacity-90 transition-opacity">
              Save Configuration
            </button>
          </div>
        </div>

        {/* Right Side - Preview */}
        <div className="space-y-6">
          <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
            <h3 className="text-white mb-4 flex items-center gap-2">
              <TrendingUp className="w-5 h-5" />
              Estimated Performance
            </h3>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="p-4 rounded-lg bg-gradient-to-br from-green-500/20 to-green-600/10 border border-green-500/30">
                <div className="text-sm text-green-400 mb-1">Daily Profit</div>
                <div className="text-2xl text-white">€{estimatedProfit.toLocaleString()}</div>
              </div>
              <div className="p-4 rounded-lg bg-gradient-to-br from-blue-500/20 to-blue-600/10 border border-blue-500/30">
                <div className="text-sm text-blue-400 mb-1">Total Capacity</div>
                <div className="text-2xl text-white">{config.batteries * config.capacity} MWh</div>
              </div>
            </div>

            <div className="text-sm text-gray-400 mb-2">Profit Trajectory</div>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={previewData}>
                <defs>
                  <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="hour" stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
                <YAxis stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '8px',
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

          <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
            <h3 className="text-white mb-4">System Summary</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Round-trip Efficiency</span>
                <span className="text-white">{((config.chargeEff * config.dischargeEff) / 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Max Daily Cycles</span>
                <span className="text-white">{Math.floor(24 / (config.capacity / config.power))}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Degradation per Cycle</span>
                <span className="text-white">€{(config.degradationCost * config.capacity * config.batteries).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Trading Strategy</span>
                <span className={config.mode === 'aggressive' ? 'text-purple-400' : 'text-blue-400'}>
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
