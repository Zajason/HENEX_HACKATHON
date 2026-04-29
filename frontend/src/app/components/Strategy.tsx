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
        <div className="eyebrow mb-3">Dispatch plan</div>
        <h1 className="mb-2 text-3xl font-semibold text-white">Trades under review</h1>
        <p className="text-slate-400">Charge and discharge windows ranked by spread, confidence, and degradation cost.</p>
      </div>

      {/* Strategy Table */}
      <div className="surface mb-6 rounded-lg p-6">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700/40">
                <th className="pb-3 pr-4 text-left text-sm text-slate-400">Status</th>
                <th className="pb-3 pr-4 text-left text-sm text-slate-400">Charge window</th>
                <th className="pb-3 pr-4 text-left text-sm text-slate-400">Discharge window</th>
                <th className="pb-3 pr-4 text-left text-sm text-slate-400">Spread</th>
                <th className="pb-3 pr-4 text-left text-sm text-slate-400">Z-score</th>
                <th className="pb-3 text-left text-sm text-slate-400">Margin</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy, index) => (
                <tr
                  key={index}
                  className={`border-b border-slate-700/30 transition-colors hover:bg-white/[0.025] ${
                    strategy.status === 'skipped' ? 'opacity-40' : ''
                  }`}
                >
                  <td className="py-4 pr-4">
                    {strategy.status === 'selected' ? (
                      <div className="flex items-center gap-2 text-emerald-200">
                        <div className="h-2 w-2 rounded-full bg-emerald-300"></div>
                        <span className="text-sm">Selected</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-slate-500">
                        <div className="h-2 w-2 rounded-full bg-slate-500"></div>
                        <span className="text-sm">Skipped</span>
                      </div>
                    )}
                  </td>
                  <td className="py-4 pr-4">
                    <div className="flex items-center gap-2">
                      <ArrowDownCircle className="h-4 w-4 text-sky-300" />
                      <span className="text-white">{strategy.chargeTime}</span>
                    </div>
                  </td>
                  <td className="py-4 pr-4">
                    <div className="flex items-center gap-2">
                      <ArrowUpCircle className="h-4 w-4 text-emerald-300" />
                      <span className="text-white">{strategy.dischargeTime}</span>
                    </div>
                  </td>
                  <td className="py-4 pr-4">
                    <span className="text-white">{strategy.spread}</span>
                  </td>
                  <td className="py-4 pr-4">
                    <span className={`px-2 py-1 rounded text-sm ${
                      strategy.zscore >= 2.5
                        ? 'bg-emerald-300/10 text-emerald-200'
                        : strategy.zscore >= 2.0
                        ? 'bg-amber-300/10 text-amber-200'
                        : 'bg-rose-300/10 text-rose-200'
                    }`}>
                      {strategy.zscore.toFixed(1)}σ
                    </span>
                  </td>
                  <td className="py-4">
                    <span className={strategy.status === 'selected' ? 'text-emerald-200' : 'text-slate-500'}>
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
            className="rounded-lg border border-emerald-300/20 bg-emerald-300/[0.055] p-4"
          >
            <div className="flex items-start gap-3">
              <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-emerald-300/12">
                <AlertCircle className="h-5 w-5 text-emerald-200" />
              </div>
              <div className="flex-1">
                <div className="text-white mb-1">
                  Trade {index + 1}: {strategy.chargeTime} → {strategy.dischargeTime}
                </div>
                <div className="text-sm text-slate-400">
                  {strategy.reason}
                </div>
              </div>
              <div className="font-medium text-emerald-200">
                {strategy.profit}
              </div>
            </div>
          </div>
        ))}

        {strategies.filter(s => s.status === 'skipped').map((strategy, index) => (
          <div
            key={index}
            className="rounded-lg border border-slate-600/20 bg-slate-500/[0.04] p-4 opacity-60"
          >
            <div className="flex items-start gap-3">
              <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-slate-500/20">
                <AlertCircle className="h-5 w-5 text-slate-400" />
              </div>
              <div className="flex-1">
                <div className="mb-1 text-slate-400">
                  Skipped: {strategy.chargeTime} → {strategy.dischargeTime}
                </div>
                <div className="text-sm text-slate-500">
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
