import { useEffect, useState } from 'react';
import { Battery, Plus, Trash2, TrendingUp } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { BatteryUnitConfig } from '../data/AppDataContext';
import { useAppData } from '../data/AppDataContext';

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
  const { assetConfig, saveAssetConfig } = useAppData();
  const [config, setConfig] = useState(assetConfig);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const totalBatteryUnits = config.batteries.reduce((sum, battery) => sum + battery.quantity, 0);
  const totalCapacity = config.batteries.reduce((sum, battery) => sum + battery.quantity * battery.capacity, 0);
  const totalPower = config.batteries.reduce((sum, battery) => sum + battery.quantity * battery.power, 0);
  const totalDegradationPerCycle = config.batteries.reduce(
    (sum, battery) => sum + battery.quantity * battery.degradationCost * battery.capacity,
    0,
  );
  const weightedRoundTripEfficiency =
    totalCapacity > 0
      ? config.batteries.reduce(
          (sum, battery) =>
            sum + ((battery.chargeEff * battery.dischargeEff) / 100) * battery.quantity * battery.capacity,
          0,
        ) / totalCapacity
      : 0;
  const estimatedProfit = Math.round(totalCapacity * 23.75);

  useEffect(() => {
    setConfig(assetConfig);
  }, [assetConfig]);

  const updateConfig = (nextConfig: typeof config) => {
    setConfig(nextConfig);
    setSaveStatus('idle');
  };

  const updateBattery = (id: string, updates: Partial<BatteryUnitConfig>) => {
    updateConfig({
      batteries: config.batteries.map((battery) => (battery.id === id ? { ...battery, ...updates } : battery)),
    });
  };

  const addBattery = () => {
    const nextNumber = config.batteries.length + 1;
    updateConfig({
      batteries: [
        ...config.batteries,
        {
          id: `battery-${Date.now()}`,
          name: `Battery block ${nextNumber}`,
          quantity: 1,
          capacity: 10,
          power: 5,
          socMin: 10,
          socMax: 90,
          socInitial: 15,
          chargeEff: 92,
          dischargeEff: 90,
          degradationCost: 2.5,
        },
      ],
    });
  };

  const removeBattery = (id: string) => {
    if (config.batteries.length === 1) return;
    updateConfig({ batteries: config.batteries.filter((battery) => battery.id !== id) });
  };

  const handleSave = async () => {
    setSaveStatus('saving');
    try {
      await saveAssetConfig(config);
      setSaveStatus('saved');
    } catch {
      setSaveStatus('error');
    }
  };

  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <div className="eyebrow mb-3">Asset setup</div>
        <h1 className="mb-2 text-3xl font-semibold text-white">Battery fleet</h1>
        <p className="text-slate-400">Build battery blocks and tune the specs shared by each block.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="surface rounded-md p-6">
          <div className="mb-6 flex items-center justify-between gap-4">
            <h3 className="flex items-center gap-2 text-white">
              <Battery className="h-5 w-5" />
              Battery grid
            </h3>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-sky-300/40 bg-sky-300/15 text-sky-100 transition-colors hover:bg-sky-300/20"
              onClick={addBattery}
              aria-label="Add battery"
              title="Add battery"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-6">
            <div className="overflow-x-auto">
              <div className="min-w-[1240px] space-y-3">
                <div className="grid grid-cols-[1.2fr_72px_repeat(8,minmax(92px,1fr))_44px] gap-3 px-1 text-xs uppercase tracking-wide text-slate-500">
                  <span>Name</span>
                  <span>Qty</span>
                  <span>Capacity (MWh)</span>
                  <span>Power (MW)</span>
                  <span>SoC min (%)</span>
                  <span>SoC max (%)</span>
                  <span>Initial SoC (%)</span>
                  <span>Charge eff (%)</span>
                  <span>Discharge eff (%)</span>
                  <span>Degradation (EUR/MWh)</span>
                  <span />
                </div>
                {config.batteries.map((battery) => (
                  <div
                    key={battery.id}
                    className="grid grid-cols-[1.2fr_72px_repeat(8,minmax(92px,1fr))_44px] gap-3 rounded-md border border-slate-700/50 bg-white/[0.03] p-3"
                  >
                    <input
                      value={battery.name}
                      onChange={(e) => updateBattery(battery.id, { name: e.target.value })}
                      className="field-control h-10"
                      aria-label="Battery name"
                    />
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={battery.quantity}
                      onChange={(e) =>
                        updateBattery(battery.id, { quantity: Math.max(parseInt(e.target.value, 10) || 1, 1) })
                      }
                      className="field-control h-10"
                      aria-label="Quantity"
                    />
                    <input
                      type="number"
                      value={battery.capacity}
                      onChange={(e) => updateBattery(battery.id, { capacity: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Capacity MWh"
                    />
                    <input
                      type="number"
                      value={battery.power}
                      onChange={(e) => updateBattery(battery.id, { power: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Power MW"
                    />
                    <input
                      type="number"
                      value={battery.socMin}
                      onChange={(e) => updateBattery(battery.id, { socMin: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Minimum state of charge percent"
                    />
                    <input
                      type="number"
                      value={battery.socMax}
                      onChange={(e) => updateBattery(battery.id, { socMax: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Maximum state of charge percent"
                    />
                    <input
                      type="number"
                      value={battery.socInitial}
                      onChange={(e) => updateBattery(battery.id, { socInitial: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Initial state of charge percent"
                    />
                    <input
                      type="number"
                      value={battery.chargeEff}
                      onChange={(e) => updateBattery(battery.id, { chargeEff: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Charge efficiency percent"
                    />
                    <input
                      type="number"
                      value={battery.dischargeEff}
                      onChange={(e) => updateBattery(battery.id, { dischargeEff: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Discharge efficiency percent"
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={battery.degradationCost}
                      onChange={(e) => updateBattery(battery.id, { degradationCost: parseFloat(e.target.value) || 0 })}
                      className="field-control h-10"
                      aria-label="Degradation cost EUR per MWh"
                    />
                    <button
                      className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-rose-300/30 bg-rose-300/10 text-rose-100 transition-colors hover:bg-rose-300/15 disabled:cursor-not-allowed disabled:opacity-40"
                      onClick={() => removeBattery(battery.id)}
                      disabled={config.batteries.length === 1}
                      aria-label={`Remove ${battery.name}`}
                      title="Remove battery"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <button
              className="w-full rounded-md border border-emerald-300/40 bg-emerald-300/15 px-4 py-3 text-emerald-100 transition-colors hover:bg-emerald-300/20"
              disabled={saveStatus === 'saving'}
              onClick={handleSave}
            >
              {saveStatus === 'saving' ? 'Saving fleet setup...' : 'Save fleet setup'}
            </button>
            {saveStatus === 'saved' && <div className="text-sm text-emerald-200">Saved to Python API and local storage.</div>}
            {saveStatus === 'error' && <div className="text-sm text-rose-200">Start the Python API, then save again.</div>}
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface rounded-md p-6">
            <h3 className="mb-4 flex items-center gap-2 text-white">
              <TrendingUp className="w-5 h-5" />
              Dispatch preview
            </h3>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-md border border-emerald-300/25 bg-emerald-300/10 p-4">
                <div className="mb-1 text-sm text-emerald-200">Daily margin</div>
                <div className="text-2xl text-white">€{estimatedProfit.toLocaleString()}</div>
              </div>
              <div className="rounded-md border border-sky-300/25 bg-sky-300/10 p-4">
                <div className="mb-1 text-sm text-sky-200">Total capacity</div>
                <div className="text-2xl text-white">{totalCapacity.toFixed(1)} MWh</div>
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

          <div className="surface rounded-md p-6">
            <h3 className="text-white mb-4">System Summary</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">Battery units</span>
                <span className="text-white">{totalBatteryUnits}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Battery blocks</span>
                <span className="text-white">{config.batteries.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Total power limit</span>
                <span className="text-white">{totalPower.toFixed(1)} MW</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Weighted round-trip efficiency</span>
                <span className="text-white">{weightedRoundTripEfficiency.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Degradation per full cycle</span>
                <span className="text-white">€{totalDegradationPerCycle.toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
