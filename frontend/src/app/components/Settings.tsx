import { Bell, Shield, Database } from 'lucide-react';

export function Settings() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <h1 className="text-3xl text-white mb-2">Settings</h1>
        <p className="text-gray-400">Configure system preferences and alerts</p>
      </div>

      <div className="space-y-6">
        {/* Notifications */}
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Bell className="w-5 h-5" />
            Notifications
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Trade Execution Alerts</div>
                <div className="text-sm text-gray-400">Get notified when trades are executed</div>
              </div>
              <input type="checkbox" className="w-5 h-5 rounded bg-white/5 border border-white/10" defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Price Spike Warnings</div>
                <div className="text-sm text-gray-400">Alert on unusual price movements</div>
              </div>
              <input type="checkbox" className="w-5 h-5 rounded bg-white/5 border border-white/10" defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white mb-1">Daily Performance Summary</div>
                <div className="text-sm text-gray-400">Receive end-of-day reports</div>
              </div>
              <input type="checkbox" className="w-5 h-5 rounded bg-white/5 border border-white/10" />
            </div>
          </div>
        </div>

        {/* Risk Management */}
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Risk Management
          </h3>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Maximum Daily Loss (€)</label>
              <input
                type="number"
                defaultValue={5000}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Minimum Z-Score Threshold</label>
              <input
                type="number"
                step="0.1"
                defaultValue={2.5}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Minimum Spread (€/MWh)</label>
              <input
                type="number"
                defaultValue={20}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Data & API */}
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" />
            Data & API
          </h3>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Price Data Provider</label>
              <select className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors">
                <option>EPEX SPOT</option>
                <option>Nord Pool</option>
                <option>OMIE</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Forecast Model</label>
              <select className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors">
                <option>LSTM Neural Network</option>
                <option>XGBoost</option>
                <option>Prophet</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Data Refresh Interval</label>
              <select className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition-colors">
                <option>15 minutes</option>
                <option>30 minutes</option>
                <option>1 hour</option>
              </select>
            </div>
          </div>
        </div>

        <button className="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white py-3 px-4 rounded-lg hover:opacity-90 transition-opacity">
          Save Settings
        </button>
      </div>
    </div>
  );
}
