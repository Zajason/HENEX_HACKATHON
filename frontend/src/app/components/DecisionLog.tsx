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
    <div className="space-y-2 max-h-80 overflow-y-auto pr-2 custom-scrollbar">
      {decisions.map((decision, index) => (
        <div
          key={index}
          className="p-3 rounded-lg border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all"
        >
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-500" />
              <span className="text-sm text-white">{decision.time}</span>
              <span className={`px-2 py-0.5 rounded text-xs ${
                decision.type === 'success' ? 'bg-green-500/20 text-green-400' :
                decision.type === 'charge' ? 'bg-blue-500/20 text-blue-400' :
                'bg-gray-500/20 text-gray-400'
              }`}>
                {decision.action}
              </span>
            </div>
            {decision.profit > 0 && (
              <span className="text-sm text-green-400">+€{decision.profit}</span>
            )}
          </div>
          <div className="text-xs text-gray-400 ml-6">
            {decision.reason}
          </div>
        </div>
      ))}
    </div>
  );
}
