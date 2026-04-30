import { TrendingUp, TrendingDown, Activity, Zap } from 'lucide-react';
import type { TradingSummary } from '../data/AppDataContext';

function metricsFromSummary(summary: TradingSummary) {
  return [{
    label: 'Expected margin',
    value: `€${summary.expectedMargin.toLocaleString()}`,
    change: `${summary.expectedChange >= 0 ? '+' : ''}${summary.expectedChange}%`,
    positive: summary.expectedChange >= 0,
    icon: TrendingUp
  },
  {
    label: 'Booked margin',
    value: `€${summary.bookedMargin.toLocaleString()}`,
    change: `${summary.bookedChange >= 0 ? '+' : ''}${summary.bookedChange}%`,
    positive: summary.bookedChange >= 0,
    icon: TrendingUp
  },
  {
    label: 'Equivalent cycles',
    value: String(summary.equivalentCycles),
    change: `${summary.cycleUtilization}%`,
    positive: summary.cycleUtilization >= 0,
    icon: Activity
  },
  {
    label: 'Efficiency Loss',
    value: `${summary.efficiencyLoss}%`,
    change: `${summary.efficiencyChange >= 0 ? '+' : ''}${summary.efficiencyChange}%`,
    positive: summary.efficiencyChange <= 0,
    icon: Zap
  }];
}

export function PerformanceMetrics({ summary }: { summary: TradingSummary }) {
  const metrics = metricsFromSummary(summary);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {metrics.map((metric, index) => {
        const Icon = metric.icon;
        return (
          <div
            key={index}
            className="rounded-md border border-slate-700/40 bg-white/[0.025] p-4 transition-all hover:border-slate-600/80 hover:bg-white/[0.04]"
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
