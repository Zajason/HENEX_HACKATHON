import { TrendingUp, TrendingDown, Activity, Zap } from 'lucide-react';

const metrics = [
  {
    label: 'Expected margin',
    value: '€2,375',
    change: '+12.5%',
    positive: true,
    icon: TrendingUp
  },
  {
    label: 'Booked margin',
    value: '€2,240',
    change: '+8.2%',
    positive: true,
    icon: TrendingUp
  },
  {
    label: 'Equivalent cycles',
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
            className="rounded-lg border border-slate-700/40 bg-white/[0.025] p-4 transition-all hover:border-slate-600/80 hover:bg-white/[0.04]"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-slate-400">{metric.label}</span>
              <Icon className="h-4 w-4 text-slate-500" />
            </div>
            <div className="mb-2 text-2xl font-semibold text-white">
              {metric.value}
            </div>
            <div className={`text-xs flex items-center gap-1 ${
              metric.positive ? 'text-emerald-200' : 'text-rose-300'
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
