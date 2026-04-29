import { TrendingUp, TrendingDown, Activity, Zap } from 'lucide-react';

const metrics = [
  {
    label: 'Expected Profit',
    value: '€2,375',
    change: '+12.5%',
    positive: true,
    icon: TrendingUp
  },
  {
    label: 'Realized Profit',
    value: '€2,240',
    change: '+8.2%',
    positive: true,
    icon: TrendingUp
  },
  {
    label: 'Total Cycles',
    value: '147',
    change: '94.2%',
    positive: true,
    icon: Activity
  },
  {
    label: 'Efficiency Loss',
    value: '5.7%',
    change: '-2.1%',
    positive: true,
    icon: Zap
  },
];

export function PerformanceMetrics() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {metrics.map((metric, index) => {
        const Icon = metric.icon;
        return (
          <div
            key={index}
            className="p-4 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-400">{metric.label}</span>
              <Icon className="w-4 h-4 text-gray-500" />
            </div>
            <div className="text-2xl text-white mb-2">
              {metric.value}
            </div>
            <div className={`text-xs flex items-center gap-1 ${
              metric.positive ? 'text-green-400' : 'text-red-400'
            }`}>
              {metric.positive ? (
                <TrendingUp className="w-3 h-3" />
              ) : (
                <TrendingDown className="w-3 h-3" />
              )}
              {metric.change}
            </div>
          </div>
        );
      })}
    </div>
  );
}
