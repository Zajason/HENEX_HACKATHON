import { Bell, Shield, Database } from 'lucide-react';

export function Settings() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <div className="eyebrow mb-3">Desk controls</div>
        <h1 className="mb-2 text-3xl font-semibold text-white">Settings</h1>
        <p className="text-slate-400">Alerts, risk guardrails, and market data sources.</p>
      </div>

      <div className="space-y-6">
        {/* Notifications */}
        <div className="surface rounded-lg p-6">
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Bell className="w-5 h-5" />
            Notifications
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Trade Execution Alerts</div>
                <div className="text-sm text-slate-400">Get notified when trades are executed</div>
              </div>
              <input type="checkbox" className="h-5 w-5 rounded border border-slate-600 bg-white/[0.04] accent-emerald-300" defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Price Spike Warnings</div>
                <div className="text-sm text-slate-400">Alert on unusual price movements</div>
              </div>
              <input type="checkbox" className="h-5 w-5 rounded border border-slate-600 bg-white/[0.04] accent-emerald-300" defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Daily Performance Summary</div>
                <div className="text-sm text-slate-400">Receive end-of-day reports</div>
              </div>
              <input type="checkbox" className="h-5 w-5 rounded border border-slate-600 bg-white/[0.04] accent-emerald-300" />
            </div>
          </div>
        </div>

        {/* Risk Management */}
        <div className="surface rounded-lg p-6">
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Risk Management
          </h3>
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm text-slate-400">Maximum daily loss (€)</label>
              <input
                type="number"
                defaultValue={5000}
                className="field-control"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm text-slate-400">Minimum z-score threshold</label>
              <input
                type="number"
                step="0.1"
                defaultValue={2.5}
                className="field-control"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm text-slate-400">Minimum spread (€/MWh)</label>
              <input
                type="number"
                defaultValue={20}
                className="field-control"
              />
            </div>
          </div>
        </div>

        {/* Data & API */}
        <div className="surface rounded-lg p-6">
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" />
            Data & API
          </h3>
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm text-slate-400">Price data provider</label>
              <select className="field-control">
                <option>EPEX SPOT</option>
                <option>Nord Pool</option>
                <option>OMIE</option>
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm text-slate-400">Forecast model</label>
              <select className="field-control">
                <option>LSTM Neural Network</option>
                <option>XGBoost</option>
                <option>Prophet</option>
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm text-slate-400">Data refresh interval</label>
              <select className="field-control">
                <option>15 minutes</option>
                <option>30 minutes</option>
                <option>1 hour</option>
              </select>
            </div>
          </div>
        </div>

        <button className="w-full rounded-lg border border-emerald-300/40 bg-emerald-300/15 px-4 py-3 text-emerald-100 transition-colors hover:bg-emerald-300/20">
          Save Settings
        </button>
      </div>
    </div>
  );
}
