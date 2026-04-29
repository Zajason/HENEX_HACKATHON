import { ArrowUpCircle, ArrowDownCircle, AlertCircle } from 'lucide-react';

const strategies = [
  {
    chargeTime: '02:00 - 06:00',
    dischargeTime: '09:00 - 13:00',
    spread: '€45.20',
    zscore: 2.8,
    profit: '€890',
    status: 'selected',
    reason: 'Z-score exceeds threshold (>2.5σ), spread is profitable after degradation costs'
  },
  {
    chargeTime: '03:00 - 05:00',
    dischargeTime: '17:00 - 19:00',
    spread: '€62.40',
    zscore: 3.2,
    profit: '€1,240',
    status: 'selected',
    reason: 'Peak evening demand with highest price differential of the day'
  },
  {
    chargeTime: '01:00 - 03:00',
    dischargeTime: '15:00 - 16:00',
    spread: '€38.50',
    zscore: 2.1,
    profit: '€580',
    status: 'selected',
    reason: 'Moderate spread but low risk, confirmed by forecast model'
  },
  {
    chargeTime: '04:00 - 06:00',
    dischargeTime: '11:00 - 12:00',
    spread: '€18.30',
    zscore: 1.4,
    profit: '€220',
    status: 'skipped',
    reason: 'Spread below minimum threshold after accounting for efficiency losses'
  },
  {
    chargeTime: '00:00 - 02:00',
    dischargeTime: '14:00 - 15:00',
    spread: '€22.10',
    zscore: 1.8,
    profit: '€310',
    status: 'skipped',
    reason: 'Z-score below confidence threshold, forecast uncertainty too high'
  },
];

export function Strategy() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <h1 className="text-3xl text-white mb-2">Trading Strategy</h1>
        <p className="text-gray-400">Optimal charge/discharge schedule with decision rationale</p>
      </div>

      {/* Strategy Table */}
      <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl mb-6" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left text-sm text-gray-400 pb-3 pr-4">Status</th>
                <th className="text-left text-sm text-gray-400 pb-3 pr-4">Charge Time</th>
                <th className="text-left text-sm text-gray-400 pb-3 pr-4">Discharge Time</th>
                <th className="text-left text-sm text-gray-400 pb-3 pr-4">Spread</th>
                <th className="text-left text-sm text-gray-400 pb-3 pr-4">Z-Score</th>
                <th className="text-left text-sm text-gray-400 pb-3">Profit</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy, index) => (
                <tr
                  key={index}
                  className={`border-b border-white/5 hover:bg-white/[0.02] transition-colors ${
                    strategy.status === 'skipped' ? 'opacity-40' : ''
                  }`}
                >
                  <td className="py-4 pr-4">
                    {strategy.status === 'selected' ? (
                      <div className="flex items-center gap-2 text-green-400">
                        <div className="w-2 h-2 rounded-full bg-green-400"></div>
                        <span className="text-sm">Selected</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-gray-500">
                        <div className="w-2 h-2 rounded-full bg-gray-500"></div>
                        <span className="text-sm">Skipped</span>
                      </div>
                    )}
                  </td>
                  <td className="py-4 pr-4">
                    <div className="flex items-center gap-2">
                      <ArrowDownCircle className="w-4 h-4 text-blue-400" />
                      <span className="text-white">{strategy.chargeTime}</span>
                    </div>
                  </td>
                  <td className="py-4 pr-4">
                    <div className="flex items-center gap-2">
                      <ArrowUpCircle className="w-4 h-4 text-green-400" />
                      <span className="text-white">{strategy.dischargeTime}</span>
                    </div>
                  </td>
                  <td className="py-4 pr-4">
                    <span className="text-white">{strategy.spread}</span>
                  </td>
                  <td className="py-4 pr-4">
                    <span className={`px-2 py-1 rounded text-sm ${
                      strategy.zscore >= 2.5
                        ? 'bg-green-500/20 text-green-400'
                        : strategy.zscore >= 2.0
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {strategy.zscore.toFixed(1)}σ
                    </span>
                  </td>
                  <td className="py-4">
                    <span className={strategy.status === 'selected' ? 'text-green-400' : 'text-gray-500'}>
                      {strategy.profit}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Explanation Panels */}
      <div className="space-y-4">
        {strategies.filter(s => s.status === 'selected').map((strategy, index) => (
          <div
            key={index}
            className="rounded-xl border border-green-500/20 bg-green-500/5 p-4 backdrop-blur-xl"
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                <AlertCircle className="w-5 h-5 text-green-400" />
              </div>
              <div className="flex-1">
                <div className="text-white mb-1">
                  Trade {index + 1}: {strategy.chargeTime} → {strategy.dischargeTime}
                </div>
                <div className="text-sm text-gray-400">
                  {strategy.reason}
                </div>
              </div>
              <div className="text-green-400 font-medium">
                {strategy.profit}
              </div>
            </div>
          </div>
        ))}

        {strategies.filter(s => s.status === 'skipped').map((strategy, index) => (
          <div
            key={index}
            className="rounded-xl border border-gray-500/20 bg-gray-500/5 p-4 backdrop-blur-xl opacity-60"
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-gray-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                <AlertCircle className="w-5 h-5 text-gray-400" />
              </div>
              <div className="flex-1">
                <div className="text-gray-400 mb-1">
                  Skipped: {strategy.chargeTime} → {strategy.dischargeTime}
                </div>
                <div className="text-sm text-gray-500">
                  {strategy.reason}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
