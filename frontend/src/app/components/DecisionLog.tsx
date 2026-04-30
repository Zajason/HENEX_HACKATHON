import { Clock } from 'lucide-react';

const decisions = [
  {
    time: '18:00',
    action: 'Discharge',
    reason: 'Peak demand period',
    profit: 1240,
    type: 'success'
  },
  {
    time: '15:00',
    action: 'Discharge',
    reason: 'High price spread detected',
    profit: 890,
    type: 'success'
  },
  {
    time: '12:00',
    action: 'Skipped',
    reason: 'Spread below threshold',
    profit: 0,
    type: 'neutral'
  },
  {
    time: '09:00',
    action: 'Discharge',
    reason: 'Z-score exceeded 2.5σ',
    profit: 780,
    type: 'success'
  },
  {
    time: '03:00',
    action: 'Charge',
    reason: 'Low overnight pricing',
    profit: 245,
    type: 'charge'
  },
  {
    time: '00:30',
    action: 'Charge',
    reason: 'Forecast dip confirmed',
    profit: 180,
    type: 'charge'
  },
];

export function DecisionLog() {
  return (
    <div className="custom-scrollbar max-h-80 space-y-2 overflow-y-auto pr-2">
      {decisions.map((decision, index) => (
        <div
          key={index}
          className="rounded-md border border-slate-700/40 bg-white/[0.02] p-3 transition-all hover:border-slate-600/80 hover:bg-white/[0.04]"
        >
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-slate-500" />
              <span className="text-sm text-white">{decision.time}</span>
              <span className={`px-2 py-0.5 rounded text-xs ${
                decision.type === 'success' ? 'bg-emerald-300/10 text-emerald-200' :
                decision.type === 'charge' ? 'bg-sky-300/10 text-sky-200' :
                'bg-slate-500/20 text-slate-400'
              }`}>
                {decision.action}
              </span>
            </div>
            {decision.profit > 0 && (
              <span className="text-sm text-emerald-200">+€{decision.profit}</span>
            )}
          </div>
          <div className="ml-6 text-xs text-slate-400">
            {decision.reason}
          </div>
        </div>
      ))}
    </div>
  );
}
